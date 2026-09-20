import json
import math
import sqlite3
import threading
import time
import zlib
import urllib.request
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..tiles import tile_bounds, tile_xy


class BuildingRegions:
    def __init__(self, root):
        self.root = Path(root)
        self.settings = json.loads((self.root/'config/building-regions.json').read_text())
        self.world = json.loads((self.root/'config/world.json').read_text(encoding='utf-8-sig'))
        self.directory = self.root/self.settings['directory']
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='building-regions')
        self.regions = {}
        self.jobs = {}
        self.catalog_state = 'idle'
        self.catalog_error = ''
        self.revision = time.time_ns()
        self.connection = None
        self.active_id = None
        self._catalog()
        self.ready = {}
        for path in self.directory.glob('*.sqlite'):
            try:
                with closing(sqlite3.connect(path)) as db:
                    metadata = json.loads(db.execute('SELECT value FROM metadata').fetchone()[0])
                self.ready[metadata['id']] = dict(metadata, bytes=path.stat().st_size)
            except (sqlite3.Error, ValueError, KeyError, TypeError):
                continue

    def _connect(self):
        import duckdb
        db = duckdb.connect(config={'threads': self.settings['threads'], 'memory_limit': self.settings['memory_limit']})
        try:
            for extension in ('spatial', 'httpfs'):
                try:
                    db.execute(f'LOAD {extension}')
                except duckdb.Error:
                    db.execute(f'INSTALL {extension}; LOAD {extension}')
            db.execute('SET http_timeout = ?', [self.settings['http_timeout_s']])
            db.execute('SET http_retries = ?', [self.settings['http_retries']])
            db.execute('SET preserve_insertion_order = false')

            db.execute('SET http_keep_alive = false')
            db.execute('SET disable_parquet_prefetching = true')
            return db
        except Exception:
            db.close()
            raise

    def _source(self, theme, kind, bounds=None):
        manifest = self.directory/f"{self.settings['release']}-{theme}-{kind}-index.json"
        if manifest.exists():
            entries = json.loads(manifest.read_text())
        else:
            def read(url):
                with urllib.request.urlopen(url, timeout=self.settings['http_timeout_s']) as response:
                    return json.load(response)
            collection = read(self.settings['catalog_url'].format(release=self.settings['release'], theme=theme, type=kind))
            urls = [link['href'] for link in collection['links'] if link['rel'] == 'item']
            with ThreadPoolExecutor(max_workers=self.settings['catalog_workers']) as workers:
                entries = [dict(bounds=item['bbox'], url=item['assets']['aws']['href']) for item in workers.map(read, urls)]
            if not entries:
                raise ValueError('В выпуске источника нет файлов зданий/областей')
            temporary = manifest.with_suffix('.tmp')
            temporary.write_text(json.dumps(entries))
            temporary.replace(manifest)
        west,south,east,north = bounds or self.world['bounds']
        matching = [entry for entry in entries if entry['bounds'][0] <= east and entry['bounds'][2] >= west
                    and entry['bounds'][1] <= north and entry['bounds'][3] >= south]
        matching.sort(key=lambda entry: (entry['bounds'][2]-entry['bounds'][0])*(entry['bounds'][3]-entry['bounds'][1]))
        return [entry['url'] for entry in matching]

    def ensure_catalog(self):
        with self.lock:
            if self.catalog_state in ('loading', 'ready'):
                return
            self.catalog_state = 'loading'
            self.catalog_error = ''
            self.pool.submit(self._catalog)

    def _catalog(self):
        try:
            catalog = json.loads((self.root/self.settings['region_catalog']).read_text(encoding='utf-8'))
            west,south,east,north = self.world['bounds']
            regions = [r for r in catalog['regions'] if r['bounds'][0] <= east and r['bounds'][2] >= west
                       and r['bounds'][1] <= north and r['bounds'][3] >= south]
            with self.lock:
                self.regions = {r['id']: r for r in regions}
                self.catalog_state = 'ready'
        except (OSError, ValueError, KeyError) as error:
            self.catalog_state, self.catalog_error = 'error', str(error)

    def _boundary(self, region):
        if 'geometry' in region:
            return region
        path = self.directory/f"boundary-{region['boundary_country']}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
        else:
            with urllib.request.urlopen(region['boundary_url'], timeout=self.settings['http_timeout_s']) as response:
                data = json.load(response)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data), encoding='utf-8')
            temporary.replace(path)
        for feature in data['features']:
            if feature['properties']['shapeID'] == region['boundary_id']:
                return dict(region, geometry=feature['geometry'])
        raise ValueError('Источник не вернул границу области')

    def status(self):
        with self.lock:
            rows = []
            for region in self.regions.values():
                identifier = region['id']
                saved = self.ready.get(identifier, {})
                job = self.jobs.get(identifier, {})
                rows.append(dict(id=identifier, name=region['name'], country=region['country'], code=region['code'],
                                 downloaded=bool(saved), count=saved.get('count', 0), bytes=saved.get('bytes', 0),
                                 release=saved.get('release'), **job))
            return dict(state=self.catalog_state, error=self.catalog_error, release=self.settings['release'], regions=rows)

    def download(self, identifier):
        with self.lock:
            if identifier not in self.regions:
                raise ValueError('Выберите область из списка')
            if self.active_id == identifier:
                raise ValueError('Дождитесь завершения текущей операции с областью')
            if self.jobs.get(identifier, {}).get('state') in ('queued', 'loading'):
                return
            self.jobs[identifier] = dict(state='queued', processed=0, error='')
            self.pool.submit(self._download, identifier, self.jobs[identifier])

    def cancel(self, identifier):
        with self.lock:
            if identifier not in self.regions:
                raise ValueError('Неизвестная область')
            if self.jobs.get(identifier, {}).get('state') in ('queued', 'loading'):
                self.jobs[identifier]['state'] = 'cancelled'
                if self.active_id == identifier and self.connection is not None:
                    self.connection.interrupt()

    def _download(self, identifier, job):
        with self.lock:
            if self.jobs[identifier] is not job or job['state'] != 'queued':
                return
            self.jobs[identifier]['state'] = 'loading'
            self.active_id = identifier
            region = self.regions[identifier]
        temporary = self.directory/f'{identifier}.partial'
        try:
            if temporary.exists():
                temporary.unlink()
            with self._connect() as remote:
                with self.lock:
                    self.connection = remote
                    if self.jobs[identifier]['state'] == 'cancelled':
                        return
                region = self._boundary(region)
                west, south, east, north = region['bounds']
                sources = self._source('buildings', 'building', region['bounds'])
                with self.lock:
                    if self.jobs[identifier]['state'] == 'cancelled':
                        return
                if not sources:
                    raise ValueError('Источник не содержит файлов для этой области')
                cursor = remote.execute('''SELECT id, height, ST_AsGeoJSON(geometry) FROM read_parquet(?)
                    WHERE bbox.xmin <= ? AND bbox.xmax >= ? AND bbox.ymin <= ? AND bbox.ymax >= ?
                    AND ST_Intersects(geometry, ST_GeomFromGeoJSON(?))''',
                    [sources, east, west, north, south, json.dumps(region['geometry'])])
                count = self._write_pack(temporary, cursor, region)
            with self.lock:
                if self.jobs[identifier]['state'] == 'cancelled':
                    return
                destination = self.directory/f'{identifier}.sqlite'
                temporary.replace(destination)
                self.ready[identifier] = dict(region, count=count, bytes=destination.stat().st_size, release=self.settings['release'])
                self.jobs[identifier] = dict(state='ready', processed=count, error='')
                self.revision += 1
        except Exception as error:
            with self.lock:
                if self.jobs[identifier]['state'] != 'cancelled':
                    self.jobs[identifier].update(state='error', error=str(error))
        finally:
            with self.lock:
                self.connection = None
                self.active_id = None
            if temporary.exists():
                temporary.unlink()

    def _write_pack(self, path, cursor, region):
        count = 0
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE buildings (id TEXT PRIMARY KEY, x INTEGER, y INTEGER, payload BLOB)')
            db.execute('CREATE INDEX tile ON buildings(x,y)')
            db.execute('CREATE TABLE metadata (value TEXT)')
            while rows := cursor.fetchmany(self.settings['batch_size']):
                if self.jobs[region['id']]['state'] == 'cancelled':
                    return count
                batch = []
                for identifier, height, geometry in rows:
                    shape = json.loads(geometry)
                    polygons = [shape['coordinates']] if shape['type'] == 'Polygon' else shape['coordinates'] if shape['type'] == 'MultiPolygon' else []
                    height = float(height) if height is not None else self.world['default_building_height_m']
                    if not math.isfinite(height) or height <= 0:
                        height = self.world['default_building_height_m']
                    for part, rings in enumerate(polygons):
                        if not rings or len(rings[0]) < 4:
                            continue
                        key = f'{identifier}:{part}'
                        x, y = tile_xy(*rings[0][0][:2], self.settings['index_level'])
                        building = dict(osm_id=key, coordinates=rings[0], holes=rings[1:], height_m=height)
                        batch.append((key, x, y, zlib.compress(json.dumps(building, separators=(',', ':')).encode())))
                db.executemany('INSERT OR IGNORE INTO buildings VALUES (?,?,?,?)', batch)
                count += len(rows)
                db.commit()
                with self.lock:
                    self.jobs[region['id']]['processed'] = count
            db.execute('INSERT INTO metadata VALUES (?)', [json.dumps(dict(region, count=count, release=self.settings['release'],index_level=self.settings['index_level']))])
            db.commit()
        return count

    def buildings(self, z, x, y):
        if z != self.world['detail_level']:
            return []
        west, south, east, north = tile_bounds(z, x, y)
        result = {}
        with self.lock:
            for identifier, region in self.ready.items():
                a, b, c, d = region['bounds']
                if east < a or west > c or north < b or south > d:
                    continue
                level=region.get('index_level',self.settings['index_level'])
                left,top=tile_xy(west,north,level)
                right,bottom=tile_xy(math.nextafter(east,west),math.nextafter(south,north),level)
                with closing(sqlite3.connect(self.directory/f'{identifier}.sqlite')) as db:
                    for key, payload in db.execute('SELECT id,payload FROM buildings WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?', [left,right,top,bottom]):
                        building=json.loads(zlib.decompress(payload))
                        lon,lat=building['coordinates'][0][:2]
                        if west<=lon<east and south<=lat<north:result[key]=building
        return list(result.values())


_stores = {}
_lock = threading.Lock()


def building_regions(root):
    root = Path(root).resolve()
    with _lock:
        if root not in _stores:
            _stores[root] = BuildingRegions(root)
        return _stores[root]
import json
import math
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .tiles import tile_bounds, tile_xy
from .vegetation.osm import height_m, sample_row
from .vegetation.roadside import RoadsideVegetation

_instances = {}
_lock = threading.Lock()


def osm_tile_cache(root):
    root = Path(root).resolve()
    with _lock:
        if root not in _instances:
            _instances[root] = OsmTileCache(root)
        return _instances[root]


def decode_buildings(data, default_height):
    if data.get('remark'):
        raise ValueError(data['remark'])
    result = []
    for element in data['elements']:
        if element.get('type') == 'relation':
            segments = [m['geometry'] for m in element.get('members',[]) if m.get('role','outer') in ('','outer') and m.get('geometry')]
            rings = []
            while segments:
                ring = segments.pop(0)
                while ring[0] != ring[-1]:
                    found = False
                    for i, segment in enumerate(segments):
                        if ring[-1] == segment[0] or ring[-1] == segment[-1]:
                            if ring[-1] == segment[-1]: segment = segment[::-1]
                            ring = ring + segment[1:]; segments.pop(i); found = True; break
                    if not found: break
                if len(ring)>=4 and ring[0]==ring[-1]: rings.append(ring)
            for index,ring in enumerate(rings):
                result.extend(decode_buildings({'elements':[dict(type='way',id=f'relation-{element["id"]}-{index}',geometry=ring,tags=element.get('tags',{}))]},default_height))
            continue
        geometry = element.get('geometry', [])
        points = [[p['lon'], p['lat']] for p in geometry]
        if len(points) < 4 or points[0] != points[-1]:
            continue
        result.append(dict(osm_id=element['id'], coordinates=points,
                           height_m=height_m(element.get('tags', {}), default_height)))
    return result


class OsmTileCache:
    def __init__(self, root):
        self.root = root
        self.settings = json.loads((root/'config/building-streaming.json').read_text())
        self.directory = (root/self.settings['cache_directory']).resolve()
        if not self.directory.is_relative_to(root) or self.directory == root:
            raise ValueError('Building cache must be inside project')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.tiles = OrderedDict()
        self.pending = set()
        self.retry = {}
        self.errors = {}
        self.revision = 0
        self.pool = ThreadPoolExecutor(max_workers=self.settings['parallel_downloads'], thread_name_prefix='buildings')
        self.disk_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='building-cache')
        self.last_prefetch = -float('inf')
        self.futures = {}
        self.network_retry_at = 0

    def observe(self, pose):
        now = time.monotonic()
        if now - self.last_prefetch < self.settings.get('prefetch_interval_s', 5):
            return
        self.last_prefetch = now
        lat, lon = pose['latitude_deg'], pose['longitude_deg']
        center_x,center_y=tile_xy(lon,lat,self.settings['level'])
        for key,future in list(getattr(self,'futures',{}).items()):
            _,tx,ty=map(int,key.split('-'))
            if future.done():self.futures.pop(key,None)
            elif max(abs(tx-center_x),abs(ty-center_y))>self.settings['maximum_pending'] and future.cancel():
                with self.lock:
                    self.pending.discard(key)
                    self.futures.pop(key,None)
        heading = math.radians(pose['yaw_deg'])
        speed = max(0, pose.get('airspeed_kt', 0)) * 0.514444
        horizon = self.settings.get('prefetch_seconds', 180)
        step = self.settings.get('prefetch_step_s', 30)
        for seconds in range(0, horizon + 1, step):
            latitude = lat + math.cos(heading) * speed * seconds / 111320
            longitude = lon + math.sin(heading) * speed * seconds / (111320 * math.cos(math.radians(lat)))
            x, y = tile_xy(longitude, latitude, self.settings['level'])
            self.get(self.settings['level'], x, y)

    def get(self, z, x, y):
        level = self.settings['level']
        w, s, e, n = tile_bounds(z, x, y)
        left, top = tile_xy(w, n, level)
        right, bottom = tile_xy(e-1e-9, s+1e-9, level)
        result = {}
        mapped = {}; roadside = {}
        with self.lock:
            for tx in range(left, right+1):
                for ty in range(top, bottom+1):
                    key = f'{level}-{tx}-{ty}'
                    if key in self.tiles:
                        self.tiles.move_to_end(key)
                        entry = self.tiles[key]
                        for target, name in ((mapped, 'mapped'), (roadside, 'roadside')):
                            for tree in entry[name]:
                                if w <= tree[0] < e and s <= tree[1] < n:
                                    target[tuple(tree[:2])] = tree
                        for building in entry['buildings']:
                            lon, lat = building['coordinates'][0]
                            if w <= lon < e and s <= lat < n:
                                result[building['osm_id']] = building
                    elif key not in self.pending and time.monotonic() >= self.retry.get(key, 0) and len(self.pending) < self.settings['maximum_pending']:
                        self.pending.add(key)
                        pool = self.disk_pool if (self.directory/(key+'.json')).exists() else self.pool
                        self.futures[key]=pool.submit(self.load, key, tile_bounds(level, tx, ty))
        return dict(buildings=list(result.values()), mapped=list(mapped.values()), roadside=list(roadside.values()))

    def load(self, key, bounds):
        path = self.directory/(key+'.json')
        try:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                    if not isinstance(data, dict) or 'elements' not in data: raise ValueError('Old cache')
                except (ValueError, OSError):
                    path.unlink(missing_ok=True)
                    raise ValueError('Corrupt building cache; will retry')
            else:
                if not self.settings['enabled']:
                    return
                if time.monotonic()<self.network_retry_at:
                    with self.lock:self.retry[key]=self.network_retry_at
                    return
                w, s, e, n = bounds
                query = f'[out:json][timeout:{self.settings["timeout_s"]}];(way[building][building!=no]({s},{w},{n},{e});relation[building][building!=no]({s},{w},{n},{e});way[highway]({s},{w},{n},{e});way[natural=tree_row]({s},{w},{n},{e});node[natural=tree]({s},{w},{n},{e}););out geom;'
                request = urllib.request.Request(self.settings['source_url'], data=urllib.parse.urlencode({'data': query}).encode(), headers={'User-Agent': 'FlightLab/1.0'})
                with urllib.request.urlopen(request, timeout=self.settings['timeout_s']+10) as response:
                    data = json.load(response)
                if data.get('remark'): raise ValueError(data['remark'])
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(data), encoding='utf-8')
                temporary.replace(path)
            buildings = decode_buildings({'elements':[e for e in data['elements'] if 'building' in e.get('tags', {})]}, self.settings['default_height_m'])
            vegetation = json.loads((self.root/'config/osm-vegetation.json').read_text())
            mapped = []
            for element in data['elements']:
                tags = element.get('tags', {})
                if tags.get('natural') == 'tree':
                    mapped.append([element['lon'], element['lat'], height_m(tags, vegetation['default_height_m'])])
                elif tags.get('natural') == 'tree_row':
                    mapped.extend([lon,lat,height_m(tags,vegetation['default_height_m'])] for lon,lat in sample_row(element.get('geometry',[]),vegetation['row_spacing_m']))
            roads = RoadsideVegetation(data['elements'],vegetation['roadside'],mapped,lambda lon,lat:0)
            with self.lock:
                self.tiles[key] = dict(buildings=buildings,mapped=mapped,roadside=roads.by_tile.get(0, []))
                while len(self.tiles) > self.settings['maximum_memory_tiles']:
                    self.tiles.popitem(last=False)
                self.errors.pop(key, None)
                self.revision += 1
                files = sorted(self.directory.glob('*.json'), key=lambda p:p.stat().st_mtime)
                total = sum(p.stat().st_size for p in files)
                for old in files:
                    if total <= self.settings['disk_limit_mb']*1024**2:
                        break
                    if old.stem in self.tiles or old.stem in self.pending:
                        continue
                    total -= old.stat().st_size
                    old.unlink()
        except Exception as error:
            with self.lock:
                self.errors[key] = str(error)
                self.retry[key] = time.monotonic()+self.settings['retry_s']
                if getattr(error,'code',None) in (429,503,504) or isinstance(error,(TimeoutError,urllib.error.URLError)):
                    self.network_retry_at=self.retry[key]
        finally:
            with self.lock:
                self.pending.discard(key)

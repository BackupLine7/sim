import json
import re
from urllib.parse import parse_qs

from .elevation.probe import elevation_probe

TILE_PATTERN = re.compile(r'/api/world/(chunk|tile)/(\d+)/(\d+)/(\d+)(?:\.jpg)?')
PREFIXES = ('/api/world/', '/api/terrain-cache', '/api/building-regions', '/api/start-elevation')

JSON_MIME = 'application/json'
JPEG_MIME = 'image/jpeg'


def as_json(payload, status=200):
    return status, json.dumps(payload, ensure_ascii=False).encode(), JSON_MIME


class WorldRoutes:
    def __init__(self, service, before_request=None):
        self.service = service
        self.before_request = before_request
        self.building_revision = None
        self.terrain_revision = None

    def handles(self, path):
        return path.startswith(PREFIXES)

    def is_tile_request(self, path):
        return bool(TILE_PATTERN.fullmatch(path))

    def invalidate_stale_chunks(self):
        revision = self.service.building_revision
        if self.building_revision != revision:
            self.service.chunk.cache_clear()
            self.building_revision = revision
        elevation = self.service.elevation
        if elevation and elevation.cache and self.terrain_revision != elevation.cache.revision:
            self.service.chunk.cache_clear()
            self.terrain_revision = elevation.cache.revision

    def respond(self, method, path, query='', body=None):
        if self.before_request:
            self.before_request()
        self.invalidate_stale_chunks()
        parameters = parse_qs(query)
        if path == '/api/start-elevation':
            return self.start_elevation(parameters)
        if path == '/api/terrain-cache':
            return self.terrain_cache(method, body)
        if path == '/api/building-regions':
            return self.building_regions(method, body)
        return self.world(method, path, parameters)

    def start_elevation(self, parameters):
        try:
            result = elevation_probe(self.service.elevation, float(parameters['lat'][0]), float(parameters['lon'][0]))
            return as_json(result)
        except (ValueError, KeyError, TypeError) as error:
            return as_json({'error': str(error)}, 400)

    def terrain_cache(self, method, body):
        try:
            cache = self.service.elevation.cache if self.service.elevation else None
            if cache is None:
                raise ValueError('Загрузка высот не настроена')
            if method == 'POST':
                data = json.loads(body)
                if data.get('action') == 'clear':
                    cache.clear()
                elif type(data.get('enabled')) is bool:
                    cache.set_enabled(data['enabled'])
                else:
                    raise ValueError('Неизвестное действие')
            elif method != 'GET':
                raise ValueError('Метод не поддерживается')
            return as_json(cache.status())
        except ValueError as error:
            return as_json({'error': str(error)}, 400)

    def building_regions(self, method, body):
        try:
            regions = self.service.regions
            if not regions:
                raise ValueError('Региональные выгрузки не настроены')
            if method == 'POST':
                data = json.loads(body)
                action = data.get('action')
                if action == 'download':
                    regions.download(data.get('id'))
                elif action == 'cancel':
                    regions.cancel(data.get('id'))
                elif action == 'catalog':
                    regions.ensure_catalog()
                else:
                    raise ValueError('Неизвестное действие')
            elif method != 'GET':
                raise ValueError('Метод не поддерживается')
            if regions.catalog_state == 'idle':
                regions.ensure_catalog()
            return as_json(regions.status())
        except (ValueError, TypeError) as error:
            return as_json({'error': str(error)}, 400)

    def world(self, method, path, parameters):
        try:
            if method != 'GET':
                raise ValueError('Метод не поддерживается')
            if path == '/api/world/settings':
                return as_json(self.service.settings)
            if path == '/api/world/building-status':
                return as_json(self.building_status())
            match = TILE_PATTERN.fullmatch(path)
            if not match:
                raise ValueError('Unknown world route')
            kind, *coordinates = match.groups()
            coordinates = tuple(map(int, coordinates))
            if kind == 'tile':
                payload, _ = self.service.image(*coordinates)
                return 200, payload, JPEG_MIME
            density = int(parameters['trees_per_tile'][0]) if 'trees_per_tile' in parameters else None
            roadside = parameters.get('roadside', ['true'])[0] == 'true'
            chunk = self.service.chunk(*coordinates, density, roadside, self.terrain_revision, self.building_revision)
            return as_json(chunk)
        except (ValueError, FileNotFoundError):
            return 404, b'Tile unavailable', 'text/plain'

    def building_status(self):
        cache = self.service.osm_tiles
        if cache is None:
            raise ValueError('Потоковая загрузка зданий не настроена')
        with cache.lock:
            return dict(revision=cache.revision, pending=list(cache.pending), errors=dict(cache.errors),
                        tiles={key: len(entry['buildings']) for key, entry in cache.tiles.items()})

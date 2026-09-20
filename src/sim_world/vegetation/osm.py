import json
import math
from collections import defaultdict

EARTH_RADIUS_M = 6378137.0


def height_m(tags, default):
    try:
        value = float(str(tags.get('height', default)).removesuffix(' m'))
        return value if math.isfinite(value) and value > 0 else default
    except (ValueError, TypeError):
        return default


def sample_row(geometry, spacing_m):
    if not geometry:
        return
    yield geometry[0]['lon'], geometry[0]['lat']
    remaining_m = spacing_m
    for a, b in zip(geometry, geometry[1:]):
        north_m = math.radians(b['lat']-a['lat'])*EARTH_RADIUS_M
        east_m = math.radians(b['lon']-a['lon'])*EARTH_RADIUS_M*math.cos(math.radians((a['lat']+b['lat'])/2))
        length_m = math.hypot(east_m, north_m)
        travelled_m = remaining_m
        while travelled_m <= length_m and length_m > 0:
            fraction = travelled_m/length_m
            yield a['lon']+(b['lon']-a['lon'])*fraction, a['lat']+(b['lat']-a['lat'])*fraction
            travelled_m += spacing_m
        remaining_m = travelled_m-length_m


class OsmVegetation:
    def __init__(self, root, tile_key):
        self.by_tile = defaultdict(list)
        self.loaded = False
        self.row_count = 0
        config = root/'config/osm-vegetation.json'
        if not config.exists():
            return
        settings = json.loads(config.read_text(encoding='utf-8'))
        path = root/settings['cache_path']
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding='utf-8'))
        elements = data['elements']
        spacing_m = settings['row_spacing_m']
        separation_m = settings['deduplication_distance_m']
        if spacing_m <= 0 or separation_m <= 0:
            raise ValueError('OSM vegetation spacing must be positive')

        cells = defaultdict(list)
        def add(lon, lat, height):
            latitude, longitude = math.radians(lat), math.radians(lon)
            xyz = (EARTH_RADIUS_M*math.cos(latitude)*math.cos(longitude), EARTH_RADIUS_M*math.cos(latitude)*math.sin(longitude), EARTH_RADIUS_M*math.sin(latitude))
            cell = tuple(math.floor(value/separation_m) for value in xyz)
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    for dz in (-1,0,1):
                        if any(math.dist(xyz,other)<separation_m for other in cells.get((cell[0]+dx,cell[1]+dy,cell[2]+dz), ())):
                            return
            cells[cell].append(xyz)
            self.by_tile[tile_key(lon,lat)].append([lon,lat,height])
        for item in sorted(elements, key=lambda item:(item['type']!='node',item['id'])):
            tags = item.get('tags',{})
            height = height_m(tags, settings['default_height_m'])
            if item['type']=='node' and tags.get('natural')=='tree':
                add(item['lon'],item['lat'],height)
            elif item['type']=='way' and tags.get('natural')=='tree_row':
                self.row_count += 1
                for lon,lat in sample_row(item.get('geometry',[]),spacing_m):
                    add(lon,lat,height)
        self.loaded = True

    def trees(self, x, y):
        return self.by_tile.get((x,y), [])
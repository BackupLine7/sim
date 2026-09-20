import json
from functools import lru_cache
from pathlib import Path

from .buildings import BuildingLayer, EMPTY
from .imagery import TileImagery
from .osm_tiles import osm_tile_cache
from .tiles import tile_bounds, tile_xy
from .vegetation import VegetationLayer


class WorldService:
    def __init__(self, root, elevation=None, exclude=None):
        self.root = Path(root)
        self.settings = json.loads((self.root / 'config/world.json').read_text(encoding='utf-8-sig'))
        self.imagery = TileImagery(self.root, self.settings)
        self.osm_tiles = osm_tile_cache(self.root) if (self.root / 'config/building-streaming.json').exists() else None
        self.buildings = BuildingLayer(self.root, self.settings, self.osm_tiles)
        self.vegetation = VegetationLayer(self.root, self.settings, self.tile_key)
        self.elevation = elevation
        self.exclude = exclude or (lambda longitude, latitude: False)

    def tile_key(self, longitude, latitude):
        return tile_xy(longitude, latitude, self.settings['detail_level'])

    @property
    def regions(self):
        return self.buildings.regions

    @property
    def building_revision(self):
        return self.buildings.revision

    def validate(self, z, x, y):
        return self.imagery.validate(z, x, y)

    def path(self, z, x, y):
        return self.imagery.path(z, x, y)

    def download(self, z, x, y):
        return self.imagery.download(z, x, y)

    def image(self, z, x, y):
        return self.imagery.image(z, x, y)

    @lru_cache(maxsize=32)
    def chunk(self, z, x, y, trees_per_tile=None, roadside_enabled=True, terrain_revision=None, building_revision=None):
        count = self.settings['trees_per_tile'] if trees_per_tile is None else trees_per_tile
        if type(count) is not int or count < 0:
            raise ValueError('Tree density must be a nonnegative integer')
        image_bytes, source_level = self.image(z, x, y)
        bounds = tile_bounds(z, x, y)
        west, south, east, north = bounds
        detailed = z == self.settings['detail_level']
        streamed = self.osm_tiles.get(z, x, y) if self.osm_tiles and detailed else EMPTY
        vegetation = self.vegetation.collect(z, x, y, bounds, image_bytes, count, roadside_enabled, streamed, self.exclude)
        trees = vegetation['trees']
        buildings = self.buildings.collect(z, x, y, bounds, streamed)
        if self.elevation and self.elevation.cache:
            with self.elevation.cache.lock:
                self.elevation.cache.request((south + north) / 2, (west + east) / 2)
        terrain = self.elevation.grid(bounds) if self.elevation and self.elevation.available else None
        if terrain:
            offset = self.elevation.geoid_separation_m
            trees = [tree + [self.elevation.elevation_asl_m(tree[1], tree[0]) + offset] for tree in trees]
            buildings = [dict(building, ground_m=self.elevation.elevation_asl_m(building['coordinates'][0][1], building['coordinates'][0][0]) + offset)
                         for building in buildings]
        return {'terrain': terrain, 'key': f'{z}/{x}/{y}', 'bounds': bounds, 'source_level': source_level,
                'trees': trees, 'osm_tree_count': vegetation['osm_tree_count'],
                'roadside_tree_count': vegetation['roadside_tree_count'],
                'buildings': buildings, 'image_url': f'/api/world/tile/{z}/{x}/{y}.jpg'}

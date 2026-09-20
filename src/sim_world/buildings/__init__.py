import json
from pathlib import Path

from .regions import BuildingRegions, building_regions

EMPTY = {'buildings': [], 'mapped': [], 'roadside': []}


def footprint(building):
    return tuple(map(tuple, building['coordinates']))


class BuildingLayer:
    def __init__(self, root, settings, osm_tiles=None):
        self.root = Path(root)
        self.settings = settings
        self.osm_tiles = osm_tiles
        self.regions = building_regions(self.root) if (self.root / 'config/building-regions.json').exists() else None
        self.local = []
        bundled = self.root / 'web/data/map.json'
        if bundled.exists():
            self.local.extend(json.loads(bundled.read_text(encoding='utf-8'))['buildings'])
        additional = self.root / settings.get('building_cache_path', 'missing-buildings.json')
        if additional.exists():
            self.local.extend(json.loads(additional.read_text(encoding='utf-8'))['buildings'])

    @property
    def revision(self):
        return (self.osm_tiles.revision if self.osm_tiles else 0,
                self.regions.revision if self.regions else 0)

    def collect(self, z, x, y, bounds, streamed=EMPTY):
        if z != self.settings['detail_level']:
            return []
        west, south, east, north = bounds
        result = [b for b in self.local if west <= b['coordinates'][0][0] < east and south <= b['coordinates'][0][1] < north]
        for source in (self.regions.buildings(z, x, y) if self.regions else [], streamed['buildings']):
            seen = {footprint(b) for b in result}
            result.extend(b for b in source if footprint(b) not in seen)
        return result

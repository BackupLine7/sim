import io
import json
import random
from pathlib import Path

from PIL import Image

from .osm import OsmVegetation, sample_row, height_m, EARTH_RADIUS_M
from .roadside import RoadsideVegetation

EMPTY = {'buildings': [], 'mapped': [], 'roadside': []}

SAMPLE_ATTEMPTS_PER_TREE = 12
GREEN_OVER_RED = 1.04
GREEN_OVER_BLUE = 1.05
GREEN_MINIMUM = 25
PROCEDURAL_HEIGHT_MIN_M = 5
PROCEDURAL_HEIGHT_SPAN_M = 9


def deduplicate(trees):
    return list({tuple(tree[:2]): tree for tree in trees}.values())


class VegetationLayer:
    def __init__(self, root, settings, tile_key):
        self.root = Path(root)
        self.settings = settings
        config = self.root / 'config/osm-vegetation.json'
        self.vegetation_settings = json.loads(config.read_text()) if config.exists() else {}
        self.osm = OsmVegetation(self.root, tile_key)
        cache_path = self.root / self.vegetation_settings.get('cache_path', 'missing-vegetation.json')
        elements = json.loads(cache_path.read_text(encoding='utf-8'))['elements'] if cache_path.exists() else []
        self.roadside = RoadsideVegetation(
            elements, self.vegetation_settings.get('roadside'),
            (tree for bucket in self.osm.by_tile.values() for tree in bucket), tile_key)

    def procedural(self, z, x, y, bounds, image_bytes, count, exclude):
        west, south, east, north = bounds
        trees = []
        rng = random.Random((z << 48) ^ (x << 24) ^ y ^ self.settings['tree_seed'])
        with Image.open(io.BytesIO(image_bytes)) as image:
            pixels = image.load()
            width, height = image.size
            for _ in range(count * SAMPLE_ATTEMPTS_PER_TREE):
                if len(trees) >= count:
                    break
                u, v = rng.random(), rng.random()
                red, green, blue = pixels[min(width - 1, int(u * width)), min(height - 1, int(v * height))]
                if not (green > red * GREEN_OVER_RED and green > blue * GREEN_OVER_BLUE and green > GREEN_MINIMUM):
                    continue
                longitude, latitude = west + (east - west) * u, north - (north - south) * v
                if exclude(longitude, latitude):
                    continue
                trees.append([longitude, latitude, PROCEDURAL_HEIGHT_MIN_M + rng.random() * PROCEDURAL_HEIGHT_SPAN_M])
        return trees

    def collect(self, z, x, y, bounds, image_bytes, count, roadside_enabled=True, streamed=EMPTY, exclude=None):
        exclude = exclude or (lambda longitude, latitude: False)
        keep = lambda source: [tree for tree in source if not exclude(tree[0], tree[1])]
        trees = self.procedural(z, x, y, bounds, image_bytes, count, exclude)
        detailed = count and z == self.settings['detail_level']
        mapped = keep(self.osm.trees(x, y)) if detailed else []
        roadside = keep(self.roadside.trees(x, y)) if detailed and roadside_enabled else []
        if count:
            mapped.extend(keep(streamed['mapped']))
            if roadside_enabled:
                roadside.extend(keep(streamed['roadside']))
        mapped = deduplicate(mapped)
        roadside = deduplicate(roadside)
        return dict(trees=trees + mapped + roadside,
                    osm_tree_count=len(mapped),
                    roadside_tree_count=len(roadside))

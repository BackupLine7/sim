import io
import urllib.request
from functools import lru_cache
from pathlib import Path

from PIL import Image

from .tiles import tile_bounds

MAXIMUM_TILE_BYTES = 2_000_000
TILE_PIXELS = 256


class TileImagery:
    def __init__(self, root, settings):
        self.root = Path(root)
        self.settings = settings
        self.directory = self.root / settings['cache_directory']

    def path(self, z, x, y):
        return self.directory / str(z) / str(x) / f'{y}.jpg'

    def validate(self, z, x, y):
        if not self.settings['overview_level'] <= z <= self.settings['detail_level'] or not (0 <= x < 2 ** z and 0 <= y < 2 ** z):
            raise ValueError('Invalid tile key')
        west, south, east, north = tile_bounds(z, x, y)
        a, b, c, d = self.settings['bounds']
        if east < a or west > c or north < b or south > d:
            raise ValueError('Outside configured region')

    def download(self, z, x, y):
        path = self.path(z, x, y)
        if path.exists():
            return path
        request = urllib.request.Request(self.settings['source_url'].format(z=z, x=x, y=y),
                                         headers={'User-Agent': 'FlightLab-local-demo/1.0'})
        with urllib.request.urlopen(request, timeout=self.settings['request_timeout_s']) as response:
            data = response.read(MAXIMUM_TILE_BYTES)
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
        return path

    def source(self, z, x, y):
        self.validate(z, x, y)
        if self.settings['allow_network_during_session'] and not self.path(z, x, y).exists():
            self.download(z, x, y)
        for level in range(z, self.settings['overview_level'] - 1, -1):
            shift = z - level
            path = self.path(level, x >> shift, y >> shift)
            if path.exists():
                return path, level
        raise FileNotFoundError('Tile not cached: run scripts/prepare_world.py before offline flight')

    @lru_cache(maxsize=32)
    def image(self, z, x, y):
        path, level = self.source(z, x, y)
        with Image.open(path) as source:
            source = source.convert('RGB')
            factor = 2 ** (z - level)
            cell = source.width / factor
            left = (x % factor) * cell
            top = (y % factor) * cell
            image = source.crop((left, top, left + cell, top + cell)).resize((TILE_PIXELS, TILE_PIXELS), Image.Resampling.BILINEAR)
            stream = io.BytesIO()
            image.save(stream, format='JPEG', quality=90)
            return stream.getvalue(), level

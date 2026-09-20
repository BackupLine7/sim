import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from sim_world.elevation.streaming import TerrainCache, tile_name

class StreamingTerrainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);(root/'config').mkdir()
        settings=json.loads(Path('config/terrain-streaming.json').read_text());settings['enabled']=False
        (root/'config/terrain-streaming.json').write_text(json.dumps(settings))
        self.cache=TerrainCache(root);self.addCleanup(self.cache.pool.shutdown)

    def test_tile_names_use_floor_in_southern_and_western_hemispheres(self):
        self.assertEqual(tile_name(-.1,-.1),'S01W001')
        self.assertEqual(tile_name(46.5,33.4),'N46E033')

    def test_offline_load_and_clear_preserve_live_surface(self):
        path=self.cache.directory/'N46E033.hgt'
        path.write_bytes(np.full((1201,1201),100,dtype='>i2').tobytes())
        self.cache.load('N46E033')
        self.assertEqual(self.cache.sample(46.5,33.5,153),100)
        self.assertGreater(self.cache.clear(),0)
        self.assertFalse(path.exists())
        self.assertEqual(self.cache.sample(46.5,33.5,153),100)

    def test_loading_does_not_raise_ground_under_aircraft(self):
        self.cache.position=(46.5,33.5);self.cache.airborne=True
        (self.cache.directory/'N46E033.hgt').write_bytes(np.full((1201,1201),1000,dtype='>i2').tobytes())
        self.cache.load('N46E033')
        self.assertEqual(self.cache.sample(46.5,33.5,153),153)
        self.assertEqual(self.cache.sample(46.8,33.5,153),1000)

    def test_corrupt_tile_does_not_replace_fallback(self):
        (self.cache.directory/'N46E033.hgt').write_bytes(b'bad')
        self.cache.load('N46E033')
        self.assertEqual(self.cache.sample(46.5,33.5,153),153)
        self.assertIn('N46E033',self.cache.errors)

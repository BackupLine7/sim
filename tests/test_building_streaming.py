import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from sim_world.osm_tiles import OsmTileCache, decode_buildings
from sim_world import tile_xy, tile_bounds


class BuildingStreamingTests(unittest.TestCase):
    def test_prefetch_follows_heading_and_is_throttled(self):
        cache = OsmTileCache.__new__(OsmTileCache)
        cache.settings = dict(level=13,prefetch_interval_s=5,prefetch_seconds=180,prefetch_step_s=30)
        cache.last_prefetch = -float('inf')
        pose = dict(latitude_deg=45,longitude_deg=34,yaw_deg=90,airspeed_kt=600)
        with patch.object(cache,'get') as get:
            cache.observe(pose)
            calls = get.call_args_list
            self.assertEqual(len(calls),7)
            self.assertGreater(calls[-1].args[1],calls[0].args[1])
            cache.observe(pose)
            self.assertEqual(get.call_count,7)

    def test_relation_outer_segments_are_joined(self):
        a={'lon':1,'lat':1};b={'lon':2,'lat':1};c={'lon':2,'lat':2}
        result=decode_buildings({'elements':[{'type':'relation','id':4,'tags':{'height':'15'},'members':[
            {'role':'outer','geometry':[a,b]}, {'role':'outer','geometry':[a,c,b]}]}]},9)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['coordinates'],[[1,1],[2,1],[2,2],[1,1]])
    def test_partial_response_is_not_cached_as_complete(self):
        with self.assertRaises(ValueError):
            decode_buildings({'remark':'timeout', 'elements':[]}, 9)

    def test_cached_geometry_loads_without_network_and_generates_roadside(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'config').mkdir()
            for name in ('building-streaming.json','osm-vegetation.json'):
                shutil.copy(source/'config'/name, root/'config'/name)
            cache = OsmTileCache(root)
            x,y = tile_xy(33.59,46.51,13)
            key = f'13-{x}-{y}'
            geometry = [{'lon':33.59,'lat':46.51},{'lon':33.591,'lat':46.51},{'lon':33.591,'lat':46.511},{'lon':33.59,'lat':46.51}]
            elements = [dict(type='way',id=1,tags={'building':'yes','height':'12'},geometry=geometry),
                        dict(type='way',id=2,tags={'highway':'secondary'},geometry=geometry[:2])]
            (cache.directory/(key+'.json')).write_text(json.dumps({'elements':elements}))
            try:
                with patch('urllib.request.urlopen', side_effect=AssertionError('network')):
                    cache.load(key,tile_bounds(13,x,y))
                    data = cache.get(13,x,y)
                self.assertEqual(data['buildings'][0]['height_m'],12)
                self.assertTrue(data['roadside'])
                self.assertFalse(cache.errors)
                self.assertEqual(cache.revision,1)
                from urllib.error import HTTPError
                with patch('urllib.request.urlopen',side_effect=HTTPError('https://example.test',429,'limited',{},None)) as request:
                    cache.load('13-1-1',tile_bounds(13,1,1))
                    cache.load('13-1-2',tile_bounds(13,1,2))
                    self.assertEqual(request.call_count,1,'global backoff must stop the rest of the queue')
                    self.assertGreater(cache.retry['13-1-2'],0)
            finally:
                cache.pool.shutdown()
                cache.disk_pool.shutdown()

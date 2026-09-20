import json, unittest
from pathlib import Path
from sim_world.vegetation.roadside import RoadsideVegetation

class RoadsideTests(unittest.TestCase):
    def test_offset_determinism_exclusions_and_tile_partition(self):
        settings=json.loads(Path('config/osm-vegetation.json').read_text())['roadside']
        road={'type':'way','id':1,'tags':{'highway':'secondary','width':'8'},'geometry':[{'lon':0,'lat':0},{'lon':0.002,'lat':0}]}
        tile=lambda lon,lat:(int(lon/0.001),0)
        first=RoadsideVegetation([road],settings,[],tile)
        trees=[t for b in first.by_tile.values() for t in b]
        self.assertTrue(trees)
        self.assertTrue(all(abs(t[1]*111319.49)>10 for t in trees))
        self.assertEqual(first.by_tile,RoadsideVegetation([road],settings,[],tile).by_tile)
        self.assertEqual(len(first.by_tile),2)
        self.assertFalse(RoadsideVegetation([road],dict(settings,enabled=False),[],tile).by_tile)
        road['tags']['bridge']='yes'
        self.assertFalse(RoadsideVegetation([road],settings,[],tile).by_tile)
        road['tags'].pop('bridge')
        fewer=RoadsideVegetation([road],settings,[trees[0]],tile)
        self.assertLess(sum(map(len,fewer.by_tile.values())),len(trees))

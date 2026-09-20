import json, math, tempfile, unittest
from pathlib import Path
from sim_world.vegetation.osm import OsmVegetation, sample_row, height_m, EARTH_RADIUS_M

class OsmVegetationTests(unittest.TestCase):
    def test_spacing_crosses_vertices(self):
        degree = math.degrees(1/EARTH_RADIUS_M)
        points=list(sample_row([{'lon':0,'lat':0},{'lon':5*degree,'lat':0},{'lon':20*degree,'lat':0}],8))
        self.assertEqual(len(points),3)
        self.assertAlmostEqual(points[1][0]/degree,8)
        self.assertAlmostEqual(points[2][0]/degree,16)

    def test_nodes_precede_rows_and_missing_cache_is_optional(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertFalse(OsmVegetation(root,lambda lon,lat:(0,0)).loaded)
            (root/'config').mkdir()
            (root/'config/osm-vegetation.json').write_text(json.dumps(dict(cache_path='trees.json',row_spacing_m=8,default_height_m=9,deduplication_distance_m=3)))
            (root/'trees.json').write_text(json.dumps({'elements':[
                {'type':'way','id':1,'tags':{'natural':'tree_row'},'geometry':[{'lon':0,'lat':0},{'lon':0.0002,'lat':0}]},
                {'type':'node','id':2,'lon':0,'lat':0,'tags':{'natural':'tree','height':'12 m'}}]}))
            trees=OsmVegetation(root,lambda lon,lat:(0 if lon<0.0001 else 1,0))
            self.assertEqual(trees.row_count,1)
            self.assertEqual(trees.trees(0,0)[0],[0,0,12])
            self.assertEqual(sum(map(len,trees.by_tile.values())),3)
            self.assertEqual(len(trees.trees(1,0)),1)
            self.assertEqual(height_m({'height':'nan'},9),9)

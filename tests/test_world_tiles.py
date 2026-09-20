import io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sim_bridge.world import simulator_world
from sim_world import tile_xy, tile_bounds
class WorldTests(unittest.TestCase):
 def test_expanded_region_accepts_overview_and_intermediate_levels(self):
  store=simulator_world(Path('.'))
  for lon,lat in [(18.1,40.1),(65.9,71.9),(25,70),(60,56),(34.38,49.57)]:
   for level in range(store.settings['overview_level'],store.settings['detail_level']+1):
    x,y=tile_xy(lon,lat,level)
    store.validate(level,x,y)
 def test_bounds_roundtrip(self):
  for lon,lat in [(30.5234,50.4501),(36.23,49.99),(40.4,46.1)]:
   x,y=tile_xy(lon,lat,14);w,s,e,n=tile_bounds(14,x,y)
   self.assertTrue(w<=lon<e and s<lat<=n)
 def test_offline_fallback_and_deterministic_bounded_trees(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'config').mkdir()
   settings=json.loads(Path('config/world.json').read_text(encoding='utf-8-sig'))
   (root/'config/world.json').write_text(json.dumps(settings))
   store=simulator_world(root);detail=settings['detail_level'];x,y=tile_xy(36.23,49.99,detail)
   path=store.path(9,x>>(detail-9),y>>(detail-9));path.parent.mkdir(parents=True)
   Image.new('RGB',(256,256),(40,100,30)).save(path)
   with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
    image,level=store.image(detail,x,y)
    self.assertEqual(level,9)
    self.assertEqual(Image.open(io.BytesIO(image)).size,(256,256))
    first=store.chunk(detail,x,y)
    store.chunk.cache_clear()
    self.assertEqual(first,store.chunk(detail,x,y))
    self.assertEqual(len(first['trees']),settings['trees_per_tile'])
    self.assertEqual(store.chunk(detail,x,y,0)['trees'],[])
    self.assertEqual(store.chunk(detail,x,y,180)['trees'],first['trees'][:180])
    self.assertEqual(len(store.chunk(detail,x,y,720)['trees']),720)
    from types import SimpleNamespace
    streamed = []
    store.osm_tiles = SimpleNamespace(get=lambda *args:dict(buildings=list(streamed),mapped=[],roadside=[]))
    self.assertEqual(store.chunk(detail,x,y,0,True,0,0)['buildings'],[])
    west,south,east,north=tile_bounds(detail,x,y)
    streamed.append(dict(osm_id=1,coordinates=[[west,south],[east,south],[west,north],[west,south]],height_m=9))
    self.assertEqual(len(store.chunk(detail,x,y,0,True,0,1)['buildings']),1,'new revision must bypass an earlier empty chunk')
    for invalid in [-1,1.5,True]:
     with self.assertRaises(ValueError):store.chunk(detail,x,y,invalid)
    self.assertEqual(store.imagery.image.cache_info().maxsize,32)
   with self.assertRaises(ValueError):store.image(30,x,y)
   with self.assertRaises(ValueError):store.image(detail,0,0)
if __name__=='__main__':unittest.main()

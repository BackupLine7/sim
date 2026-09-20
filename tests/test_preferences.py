import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sim_bridge.preferences import PreferencesStore
class PreferencesTests(unittest.TestCase):
 def setUp(self):self.defaults=json.loads(Path('config/preferences.json').read_text(encoding='utf-8-sig'))
 def test_validation_order_and_finite_values(self):
  store=PreferencesStore('.')
  for value in [float('nan'),float('inf'),True,-1,0]:
   data=json.loads(json.dumps(self.defaults));data['aircraft']['maximum_speed_kmh']=value
   with self.assertRaises(ValueError):store.validate(data)
  data=json.loads(json.dumps(self.defaults));data['aircraft']['minimum_speed_kmh']=90
  with self.assertRaises(ValueError):store.validate(data)
 def test_roundtrip_and_units(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'config').mkdir();(root/'config/preferences.json').write_text(json.dumps(self.defaults))
   (root/'config/aircraft-envelope.json').write_text(Path('config/aircraft-envelope.json').read_text())
   store=PreferencesStore(root);data=store.read();data['controls']['invert_roll']=True;data['aircraft']['maximum_speed_kmh']=108
   store.save(data)
   self.assertTrue(PreferencesStore(root).read()['controls']['invert_roll'])
   self.assertEqual(store.parameters()['AIRSPEED_MAX'],30)
   self.assertEqual(store.parameters()['TKOFF_ALT'],120)
 def test_model_limit_cannot_be_raised_by_settings(self):
  store=PreferencesStore('.')
  for field in store.SPEED_FIELDS:
   data=json.loads(json.dumps(self.defaults));data['aircraft'][field]=store.envelope()['maximum_commanded_airspeed_kmh']+1
   with self.assertRaises(ValueError):store.validate(data)
 def test_cruise_can_equal_validated_limit(self):
  data=json.loads(json.dumps(self.defaults));data['aircraft']['cruise_speed_kmh']=108
  PreferencesStore('.').validate(data)
 def test_legacy_excessive_speeds_are_migrated(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'config').mkdir()
   for name in ['preferences.json','aircraft-envelope.json']:(root/'config'/name).write_text(Path('config',name).read_text())
   data=json.loads(json.dumps(self.defaults));data['aircraft'].update(cruise_speed_kmh=349,maximum_speed_kmh=350)
   (root/'config/local.preferences.json').write_text(json.dumps(data))
   migrated=PreferencesStore(root).read()['aircraft']
   self.assertEqual(migrated['maximum_speed_kmh'],108)
   self.assertEqual(migrated['cruise_speed_kmh'],108)
if __name__=='__main__':unittest.main()

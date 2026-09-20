import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from sim_bridge.start_locations import StartLocations

class StartLocationsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'config/simulation.yaml').write_text('polygon:\n  home_latitude_deg: 49\n  home_longitude_deg: 34\n  home_elevation_asl_m: 153\n  home_heading_deg: 90\n')
        self.store=StartLocations(self.root)
        self.point=dict(name='Новая площадка',latitude_deg=50,longitude_deg=35,elevation_asl_m=200,heading_deg=120)

    def test_save_does_not_move_active_start(self):
        point=self.store.save(self.point)
        self.assertEqual(self.store.catalog()['active_id'],'default')
        self.assertFalse(self.store.active_path.exists())
        self.store.activate(point['id'])
        self.assertEqual(self.store.catalog()['active_id'],point['id'])
        self.store.activate('default')
        self.assertEqual(self.store.catalog()['active_id'],'default')

    def test_validation_and_missing_selection(self):
        for field,value in [('latitude_deg',91),('heading_deg',360),('elevation_asl_m',float('nan')),('longitude_deg',True)]:
            with self.assertRaises(ValueError):self.store.save(dict(self.point,**{field:value}))
        with self.assertRaises(ValueError):self.store.activate('../elsewhere')
        self.assertFalse(self.store.active_path.exists())

    def test_edit_keeps_id_and_active_snapshot_until_activation(self):
        point=self.store.save(self.point)
        self.store.activate(point['id'])
        snapshot=self.store.active_path.read_bytes()
        changed=self.store.save(dict(point,name='Edited',latitude_deg=44.95,longitude_deg=34.1))
        self.assertEqual(changed['id'],point['id'])
        self.assertEqual(len(self.store.catalog()['locations']),2)
        self.assertEqual(self.store.find(point['id'])['latitude_deg'],44.95)
        self.assertEqual(self.store.active_path.read_bytes(),snapshot)
        self.store.activate(point['id'])
        self.assertNotEqual(self.store.active_path.read_bytes(),snapshot)
        with self.assertRaises(ValueError):self.store.save(dict(point,id='missing'))

    def test_delete_preserves_active_flight_snapshot(self):
        point=self.store.save(self.point)
        self.store.activate(point['id'])
        snapshot=self.store.active_path.read_bytes()
        self.store.delete(point['id'])
        self.assertEqual(self.store.active_path.read_bytes(),snapshot)
        self.assertEqual(len(self.store.catalog()['locations']),1)
        with self.assertRaises(ValueError):self.store.delete('default')
        with self.assertRaises(ValueError):self.store.delete('../missing')

    def test_selected_start_is_used_by_simulation_config(self):
        from sim_launcher.config import load_simulation_config
        original=Path(__file__).resolve().parents[1]/'config/simulation.yaml'
        (self.root/'config/simulation.yaml').write_text(original.read_text(encoding='utf-8'),encoding='utf-8')
        point=self.store.save(self.point)
        self.store.activate(point['id'])
        with patch('sim_launcher.config._validate'):
            config=load_simulation_config(self.root/'config/simulation.yaml')
        self.assertEqual(config.polygon.home_latitude_deg,50)
        self.assertEqual(config.polygon.home_longitude_deg,35)
        self.assertEqual(config.polygon.home_elevation_asl_m,200)
        self.assertEqual(config.polygon.home_heading_deg,120)

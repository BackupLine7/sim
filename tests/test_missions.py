import json
import tempfile
import unittest
from pathlib import Path
from sim_bridge.missions import MissionStore


class MissionTests(unittest.TestCase):
    def test_save_goal_normalizes_height_and_keeps_order(self):
        mission={'name':'Ordered','waypoints':[
            dict(name='B',type='goal',latitude_deg=49,longitude_deg=34,altitude_relative_m=500,terrain_elevation_asl_m=999),
            dict(name='A',type='transit',latitude_deg=49.1,longitude_deg=34.1,altitude_relative_m=200)]}
        with tempfile.TemporaryDirectory() as directory:
            store=MissionStore(Path(directory));store.save(mission)
            points=store.read()['missions'][0]['waypoints']
            self.assertEqual([p['name'] for p in points],['B','A'])
            self.assertEqual(points[0]['altitude_relative_m'],0)
            self.assertNotIn('terrain_elevation_asl_m',points[0])
    def test_invalid_file_does_not_hide_valid_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = {'name': 'Circuit', 'waypoints': [
                {'latitude_deg': 49, 'longitude_deg': 34},
                {'latitude_deg': 49.1, 'longitude_deg': 34.1}]}
            (root / 'valid.json').write_text(json.dumps(valid))
            (root / 'broken.json').write_text('{')
            result = MissionStore(root).read()
            self.assertEqual(result['missions'][0]['id'], 'valid')
            self.assertEqual(len(result['errors']), 1)
            valid['waypoints'][0]['latitude_deg'] = 91
            with self.assertRaises(ValueError):
                MissionStore.validate(valid)

    def test_rejects_nonfinite_and_boolean_coordinates(self):
        for value in [float('nan'), float('inf'), True, '49']:
            with self.assertRaises(ValueError):
                MissionStore.validate({'name': 'Invalid', 'waypoints': [
                    {'latitude_deg': value, 'longitude_deg': 34},
                    {'latitude_deg': 49, 'longitude_deg': 34}]})

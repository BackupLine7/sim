import tempfile, unittest
from pathlib import Path
from sim_bridge.missions import MissionStore
class MissionSaveTests(unittest.TestCase):
    def test_create_update_and_reject_invalid_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            store=MissionStore(Path(folder))
            mission={'name':'Route','waypoints':[{'latitude_deg':49,'longitude_deg':34,'type':'transit'},{'latitude_deg':49.1,'longitude_deg':34.1,'type':'goal'}]}
            saved=store.save(mission)
            self.assertTrue(saved['id'].startswith('custom-'))
            mission['name']='Edited'
            store.save(mission,saved['id'])
            self.assertEqual(store.read()['missions'][0]['name'],'Edited')
            for identifier in ['../outside','training-test','A/B']:
                with self.assertRaises(ValueError):store.save(mission,identifier)
            mission['waypoints'][0]['type']='unknown'
            with self.assertRaises(ValueError):store.save(mission,saved['id'])
            self.assertEqual(store.read()['missions'][0]['waypoints'][0]['type'],'transit')

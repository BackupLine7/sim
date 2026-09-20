import json
import shutil
import tempfile
import unittest
from pathlib import Path
from sim_bridge.missions import MissionStore

class MissionDeleteTests(unittest.TestCase):
    def test_deleted_file_and_training_missions_stay_out_of_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'config/missions').mkdir(parents=True)
            (root/'web/data').mkdir(parents=True)
            for name in ('mission-navigation.json','training-lessons.json'):
                shutil.copy(Path('config')/name,root/'config'/name)
            shutil.copy('web/data/session.json',root/'web/data/session.json')
            store=MissionStore(root/'config/missions')
            saved=store.save(dict(name='Test',waypoints=[dict(latitude_deg=45,longitude_deg=34),dict(latitude_deg=45.1,longitude_deg=34.1)]))
            training=next(m['id'] for m in store.catalog(root)['missions'] if m['id'].startswith('training-'))
            for identifier in (saved['id'],training):store.delete(identifier)
            identifiers={m['id'] for m in store.catalog(root)['missions']}
            self.assertNotIn(saved['id'],identifiers)
            self.assertNotIn(training,identifiers)
            self.assertTrue((store.directory/(saved['id']+'.json')).exists())
            with self.assertRaises(ValueError):store.delete('../outside')

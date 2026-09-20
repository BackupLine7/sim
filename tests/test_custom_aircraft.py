import json
import shutil
import tempfile
import unittest
from pathlib import Path
from sim_bridge.aircraft_catalog import AircraftCatalog
from sim_bridge.custom_aircraft import create_aircraft


class CustomAircraftTests(unittest.TestCase):
    def test_creation_preserves_physics_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config').mkdir()
            shutil.copy(Path(__file__).resolve().parents[1]/'config/aircraft-catalog.json',root/'config/aircraft-catalog.json')
            catalog=AircraftCatalog(root)
            custom=create_aircraft(catalog,dict(base_id='f16',name='My jet',scale=2))
            reloaded=AircraftCatalog(root).get(custom['id'])
            self.assertEqual(reloaded['model'],'f16')
            self.assertEqual(reloaded['parameters'],catalog.get('f16')['parameters'])
            self.assertEqual(reloaded['visual']['scale'],2)
            self.assertEqual(catalog.selected()['id'],'rascal')
            with self.assertRaises(ValueError):
                create_aircraft(catalog,dict(base_id='f16',name='Bad',glb_base64='invalid'))
            self.assertEqual(len(AircraftCatalog(root).data['aircraft']),4)

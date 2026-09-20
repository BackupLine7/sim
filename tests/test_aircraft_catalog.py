import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sim_bridge.aircraft_catalog import AircraftCatalog
from sim_bridge.preferences import PreferencesStore


class AircraftCatalogTest(unittest.TestCase):
    def test_selection_and_preferences_are_separate(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            for name in ('aircraft-catalog.json', 'preferences.json', 'aircraft-envelope.json'):
                shutil.copy(source / 'config' / name, root / 'config' / name)
            catalog = AircraftCatalog(root)
            self.assertEqual(catalog.selected()['id'], 'rascal')
            with self.assertRaises(ValueError):
                catalog.get('../invalid')
            store = PreferencesStore(root)
            rascal_path = store.path
            catalog.path.write_text(json.dumps({'id': 'f16'}))
            self.assertNotEqual(store.path, rascal_path)
            self.assertEqual(store.read()['aircraft']['cruise_speed_kmh'], 600)
            self.assertEqual(store.envelope()['model'], 'f16')

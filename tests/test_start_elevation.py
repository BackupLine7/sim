import math
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from sim_world.elevation.streaming import TerrainCache
from sim_world.elevation.probe import elevation_probe


class StartElevationTests(unittest.TestCase):
    def test_start_uses_raw_msl_without_current_flight_protection(self):
        cache=TerrainCache.__new__(TerrainCache)
        cache.lock=threading.RLock()
        cache.tiles={'N48E035':(np.array([[100,200],[300,400]]),(48.5,35.5))}
        cache.suppressed=set();cache.request=Mock()
        result=elevation_probe(SimpleNamespace(cache=cache),48.5,35.5)
        self.assertEqual(result,dict(ready=True,elevation_asl_m=250))

    def test_missing_tile_stays_pending_instead_of_old_home_altitude(self):
        cache=SimpleNamespace(lock=threading.RLock(),suppressed=set(),request=Mock(),sample=Mock(return_value=math.nan),errors={},tiles={},enabled=True)
        self.assertEqual(elevation_probe(SimpleNamespace(cache=cache),48,35),dict(ready=False))
        cache.request.assert_called_once_with(48,35)

    def test_invalid_coordinates_rejected(self):
        with self.assertRaises(ValueError):elevation_probe(SimpleNamespace(cache=None),math.nan,35)

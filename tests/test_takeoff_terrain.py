import unittest
from types import SimpleNamespace
from unittest import mock
from sim_bridge import takeoff_terrain
from sim_bridge.takeoff_terrain import departure_altitude

class TakeoffTerrainTests(unittest.TestCase):
    def test_mountain_ahead_raises_target_above_peak(self):
        home=dict(home_latitude_deg=0,home_longitude_deg=0,home_heading_deg=90,home_elevation_asl_m=200)
        settings=dict(lookahead_m=12000,sample_step_m=100,corridor_half_width_m=500,clearance_m=150)
        height=departure_altitude(home,settings,lambda lat,lon:1100 if lon*111320>7000 else 200)
        self.assertEqual(height,1050)
        self.assertEqual(departure_altitude(home,settings,lambda lat,lon:200),150)

    def test_missing_terrain_is_not_treated_as_flat(self):
        home=dict(home_latitude_deg=0,home_longitude_deg=0,home_heading_deg=0,home_elevation_asl_m=200)
        settings=dict(lookahead_m=1000,sample_step_m=100,corridor_half_width_m=500,clearance_m=150)
        def missing(lat,lon):raise ValueError('missing')
        with self.assertRaises(ValueError):departure_altitude(home,settings,missing)

    def test_plan_takeoff_samples_world_elevation(self):
        # Regression: plan_takeoff runs on the MAVLink worker thread, so a broken
        # sampler there stops every takeoff instead of failing one request.
        world=SimpleNamespace(cache=None,source=SimpleNamespace(elevation_asl_m=lambda lat,lon:900))
        runtime=SimpleNamespace(
            root='.',
            polygon=dict(home_latitude_deg=50,home_longitude_deg=30,home_heading_deg=0,home_elevation_asl_m=200),
            settings=dict(takeoff_altitude_m=100,takeoff_terrain=dict(lookahead_m=1000,sample_step_m=500,corridor_half_width_m=100,clearance_m=150)),
        )
        with mock.patch.object(takeoff_terrain,'SimulatorElevation',return_value=world):
            self.assertEqual(takeoff_terrain.plan_takeoff(runtime),850)

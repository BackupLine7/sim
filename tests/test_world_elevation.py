import unittest
from pathlib import Path
from sim_bridge.world_elevation import SimulatorElevation
from sim_world import tile_xy, tile_bounds

class TerrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.elevation=SimulatorElevation(Path('.'))

    def test_home_and_real_slope(self):
        if not self.elevation.available:self.skipTest('Prepare DEM first')
        home=self.elevation.home
        self.assertEqual(self.elevation.elevation_asl_m(home.home_latitude_deg,home.home_longitude_deg),home.home_elevation_asl_m)
        self.assertGreater(self.elevation.elevation_asl_m(49.581875,34.568934)-self.elevation.elevation_asl_m(49.577,34.591),50)

    def test_shared_tile_edges_and_grid_budget(self):
        x,y=tile_xy(34.568934,49.581875,14)
        a=self.elevation.grid(tile_bounds(14,x,y));b=self.elevation.grid(tile_bounds(14,x+1,y))
        n=a['size']
        self.assertEqual(a['heights_m'][n-1::n],b['heights_m'][::n])
        self.assertEqual(a['latitudes'],b['latitudes'])
        self.assertLess(a['terrain_grid_ms'],200)

    def test_geoid_offset_only_changes_rendered_heights(self):
        elevation=self.elevation
        old=elevation.geoid_separation_m
        x,y=tile_xy(34.568934,49.581875,14)
        physical=elevation.elevation_asl_m(49.581875,34.568934)
        try:
            elevation.geoid_separation_m=0
            a=elevation.grid(tile_bounds(14,x,y))
            elevation.geoid_separation_m=30
            b=elevation.grid(tile_bounds(14,x,y))
            self.assertEqual(elevation.elevation_asl_m(49.581875,34.568934),physical)
            for first,second in zip(a['heights_m'],b['heights_m']):self.assertAlmostEqual(second-first,30,places=3)
        finally:elevation.geoid_separation_m=old

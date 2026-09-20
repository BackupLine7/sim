import unittest
from sim_bridge.waypoint_crossing import crosses_waypoint


class CrossingTests(unittest.TestCase):
    def test_fast_crossing_and_near_misses(self):
        p=dict(latitude_deg=0,longitude_deg=0,altitude_relative_m=100,radius_m=10)
        self.assertTrue(crosses_waypoint((0,-.001,100),(0,.001,100),p,5))
        self.assertFalse(crosses_waypoint((.001,-.001,100),(.001,.001,100),p,5))
        self.assertFalse(crosses_waypoint((0,-.001,120),(0,.001,120),p,5))
        # Horizontal and vertical acceptance must coincide in time.
        self.assertFalse(crosses_waypoint((0,-.001,100),(0,.001,200),p,5))

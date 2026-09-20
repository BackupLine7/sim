import unittest
from sim_bridge.mission_terrain import cleared_mission


class MissionTerrainTests(unittest.TestCase):
    def test_goal_is_on_terrain_even_below_home(self):
        mission={'waypoints':[dict(type='goal',latitude_deg=0,longitude_deg=.01,altitude_relative_m=500)]}
        result=cleared_mission(mission,(0,0),900,dict(clearance_m=150,sample_step_m=100,corridor_half_width_m=100),lambda *_:400)
        self.assertEqual(result['waypoints'][0]['altitude_relative_m'],-500)
        self.assertEqual(mission['waypoints'][0]['altitude_relative_m'],500)
    def test_mountain_between_low_waypoints_raises_route(self):
        mission={'waypoints':[dict(latitude_deg=0,longitude_deg=.02,altitude_relative_m=150),dict(latitude_deg=0,longitude_deg=.04,altitude_relative_m=150)]}
        settings=dict(clearance_m=150,sample_step_m=100,corridor_half_width_m=100)
        result=cleared_mission(mission,(0,0),100,settings,lambda lat,lon:900 if .008<lon<.012 else 100)
        self.assertTrue(all(p['altitude_relative_m']==950 for p in result['waypoints']))
        self.assertEqual(mission['waypoints'][0]['altitude_relative_m'],150)

    def test_unknown_terrain_does_not_start_a_low_route(self):
        with self.assertRaises(ValueError):
            cleared_mission({'waypoints':[dict(latitude_deg=0,longitude_deg=.01,altitude_relative_m=150)]},(0,0),100,dict(clearance_m=150,sample_step_m=100,corridor_half_width_m=100),lambda *_:float('nan'))

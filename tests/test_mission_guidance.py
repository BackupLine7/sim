import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from pymavlink import mavutil
from sim_bridge.mission_guidance import MissionGuidance
from sim_bridge.missions import MissionStore


def message(kind, **fields):
    return SimpleNamespace(get_type=lambda: kind, **fields)


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.status = {'mode': 'GUIDED'}
        self.guidance = MissionGuidance(self.status, 5, .5)
        self.link = Mock(target_system=1, target_component=1)
        self.mission = {'id': 'test', 'height_tolerance_m': 10, 'waypoints': [
            {'latitude_deg': 49, 'longitude_deg': 34, 'altitude_relative_m': 100, 'radius_m': 60},
            {'latitude_deg': 49.01, 'longitude_deg': 34.01, 'altitude_relative_m': 120, 'radius_m': 60}]}
        self.guidance.start(self.link, self.mission, 0)

    def acknowledge(self, result=0):
        self.guidance.update(self.link, message('COMMAND_ACK', command=mavutil.mavlink.MAV_CMD_DO_REPOSITION, result=result), 1)

    def position(self, index, altitude_m=None):
        point = self.mission['waypoints'][index]
        self.guidance.update(self.link, message('GLOBAL_POSITION_INT', lat=point['latitude_deg']*1e7, lon=point['longitude_deg']*1e7, relative_alt=(altitude_m if altitude_m is not None else point['altitude_relative_m'])*1000), 2)

    def test_target_frame_height_and_holding_radius(self):
        args = self.link.mav.command_int_send.call_args.args
        self.assertEqual(args[2], mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT)
        self.assertEqual(args[8], 30)
        self.assertEqual(args[-3:], (490000000, 340000000, 100))

    def test_flythrough_aims_beyond_point_without_changing_acceptance(self):
        self.status['telemetry']={'latitude_deg':48.99,'longitude_deg':34,'groundspeed_m_s':100}
        self.guidance.flythrough_settings={'bank_deg':30,'turn_radius_factor':3,'minimum_extension_m':1000}
        self.guidance.send_target(self.link,0)
        args=self.link.mav.command_int_send.call_args.args
        self.assertGreater(args[-3],490000000)
        self.assertEqual(args[-2],340000000)
        self.assertEqual(self.guidance.mission['waypoints'][0]['latitude_deg'],49)
        self.acknowledge();self.position(0)
        self.assertEqual(self.status['mission_completed'],[0])

    def test_manual_skip_and_uncheck_retarget(self):
        self.guidance.check(self.link,0,True,2)
        self.assertEqual(self.status['mission_next'],1)
        self.assertEqual(self.status['mission_completed'],[0])
        self.guidance.check(self.link,0,False,3)
        self.assertEqual(self.status['mission_next'],0)
        self.assertEqual(self.status['mission_completed'],[])

    def test_prechecked_points_are_skipped_and_all_checked_loiters(self):
        self.guidance.start(self.link,self.mission,0,[0])
        self.assertEqual(self.guidance.next,1)
        self.guidance.check(self.link,1,True,2)
        self.assertTrue(self.status['mission_complete'])
        self.link.set_mode_apm.assert_called_with('LOITER')

    def test_reached_point_updates_checklist(self):
        self.acknowledge()
        self.position(0)
        self.assertEqual(self.status['mission_completed'],[0])

    def test_high_fast_approach_uses_wide_recovery_before_retry(self):
        self.guidance.recovery_settings={'bank_deg':30,'vertical_speed_m_s':5,'approach_margin_s':10}
        self.status['telemetry']={'groundspeed_m_s':300,'yaw_deg':0}
        self.acknowledge()
        self.position(0,500)
        self.assertTrue(self.guidance.recovering)
        self.assertGreater(self.link.mav.command_int_send.call_args.args[8],15000)
        self.assertEqual(self.status['mission_completed'],[])
        self.acknowledge()
        self.position(0,100)
        self.assertFalse(self.guidance.recovering)
        self.assertEqual(self.guidance.next,0)

    def test_order_acknowledgment_and_altitude_are_required(self):
        self.position(0)
        self.assertEqual(self.guidance.next, 0)
        self.acknowledge()
        self.position(1)
        self.position(0, 50)
        self.assertEqual(self.guidance.next, 0)
        self.position(0)
        self.assertEqual(self.status['mission_next'], 1)
        self.acknowledge()
        self.position(1)
        self.assertTrue(self.status['mission_complete'])
        self.assertFalse(self.status['mission_active'])
        self.link.set_mode_apm.assert_called_once_with('LOITER')

    def test_rejection_and_timeout_stop_guidance(self):
        self.acknowledge(mavutil.mavlink.MAV_RESULT_DENIED)
        self.assertFalse(self.status['mission_active'])
        self.guidance.start(self.link, self.mission, 0)
        self.guidance.update(self.link, None, 6)
        self.assertFalse(self.status['mission_active'])
        self.assertEqual(self.link.set_mode_apm.call_count, 2)

    def test_terminal_goal_is_not_overridden_by_waiting_mode(self):
        self.mission['waypoints'][-1]['type'] = 'goal'
        self.acknowledge()
        self.position(0)
        self.acknowledge()
        self.position(1)
        self.assertTrue(self.status['mission_complete'])
        self.assertEqual(self.status['mission_end'], 'goal')
        self.link.set_mode_apm.assert_not_called()

    def test_terminal_landing_starts_autoland(self):
        self.mission['waypoints'][-1]['type'] = 'land'
        self.acknowledge()
        self.position(0)
        self.acknowledge()
        self.position(1)
        self.link.set_mode_apm.assert_called_once_with('AUTOLAND')

    def test_large_routes_cross_multiple_streaming_tiles(self):
        from sim_world import tile_xy
        import json
        root = Path(__file__).resolve().parents[1]
        settings = json.loads((root/'config/world.json').read_text(encoding='utf-8'))
        routes = [item for item in MissionStore.catalog(root)['missions'] if item['id'].startswith('streaming-')]
        self.assertEqual(len(routes), 3)
        for route in routes:
            tiles = [tile_xy(point['longitude_deg'], point['latitude_deg'], settings['detail_level']) for point in route['waypoints']]
            self.assertGreater(max(x for x,y in tiles)-min(x for x,y in tiles), settings['active_radius_tiles'])
            self.assertNotIn(route['waypoints'][-1]['type'], ('goal', 'land'))

    def test_manual_mode_cancels_without_overriding_pilot(self):
        self.acknowledge()
        self.status['mode'] = 'FBWA'
        self.guidance.update(self.link, message('HEARTBEAT'), 2)
        self.position(0)
        self.assertFalse(self.status['mission_active'])
        self.link.set_mode_apm.assert_not_called()

    def test_catalog_contains_geographic_training_lessons(self):
        root = Path(__file__).resolve().parents[1]
        catalog = MissionStore.catalog(root)
        self.assertEqual(catalog['errors'], [])
        lessons = [item for item in catalog['missions'] if item['id'].startswith('training-lesson-')]
        self.assertEqual(len(lessons), 15)
        import json
        session = json.loads((root/'web/data/session.json').read_text(encoding='utf-8'))
        first = lessons[0]['waypoints'][0]
        self.assertAlmostEqual(first['latitude_deg'], session['home'][1])
        self.assertAlmostEqual(first['longitude_deg'], session['home'][0])
        for mission in catalog['missions']:
            for point in mission['waypoints']:
                if point.get('type')!='goal':self.assertGreater(point['altitude_relative_m'], 0)
                self.assertGreater(point['radius_m'], 0)

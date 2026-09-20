import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from sim_bridge.auto_mission_guidance import AutoMissionGuidance


def msg(kind,**fields):return SimpleNamespace(get_type=lambda:kind,**fields)


class AutoMissionTests(unittest.TestCase):
    def setUp(self):
        self.status={'mode':'LOITER','home':[34,49,100]}
        self.link=Mock(target_system=1,target_component=1)
        self.g=AutoMissionGuidance(self.status,5,.5)
        self.g.start(self.link,{'id':'test','height_tolerance_m':20,'waypoints':[
            dict(latitude_deg=49,longitude_deg=34,altitude_relative_m=200,radius_m=50),
            dict(latitude_deg=49.1,longitude_deg=34,altitude_relative_m=200,radius_m=50)]},0)

    def upload(self):
        for seq in range(4):self.g.update(self.link,msg('MISSION_REQUEST_INT',seq=seq),1)
        self.g.update(self.link,msg('MISSION_ACK',type=0),2)
        self.status['mode']='AUTO';self.g.update(self.link,msg('HEARTBEAT'),2)
        self.g.update(self.link,msg('MISSION_CURRENT',seq=1),2)

    def test_upload_exact_coordinates_then_auto(self):
        self.upload()
        waypoint=self.link.mav.mission_item_int_send.call_args_list[1].args
        self.assertEqual(waypoint[-3:],(490000000,340000000,200))
        self.assertEqual(waypoint[4],16)
        self.link.set_mode_apm.assert_called_with('AUTO')
        self.link.mav.command_int_send.assert_not_called()

    def test_false_ap_completion_retargets_without_credit(self):
        self.upload();self.link.mav.mission_set_current_send.reset_mock()
        self.g.update(self.link,msg('MISSION_CURRENT',seq=2),3)
        # One report can precede the position sample that crosses the cylinder.
        self.link.mav.mission_set_current_send.assert_not_called()
        self.g.update(self.link,msg('MISSION_CURRENT',seq=2),3.5)
        self.assertEqual(self.status['mission_completed'],[])
        self.assertEqual(self.status['mission_missed'],1)
        self.link.mav.mission_set_current_send.assert_called_with(1,1,1)
        self.g.update(self.link,msg('GLOBAL_POSITION_INT',lat=490000000,lon=340000000,relative_alt=250000),3)
        self.assertEqual(self.status['mission_completed'],[])
        self.g.update(self.link,msg('GLOBAL_POSITION_INT',lat=490000000,lon=340000000,relative_alt=200000),4)
        self.assertEqual(self.status['mission_completed'],[0])

    def test_rejected_upload_stays_out_of_auto(self):
        self.g.update(self.link,msg('MISSION_ACK',type=1),1)
        self.assertFalse(self.status['mission_active'])
        self.link.set_mode_apm.assert_called_once_with('LOITER')

    def test_duplicate_item_refusal_does_not_abort_upload(self):
        for seq in (0,0):self.g.update(self.link,msg('MISSION_REQUEST',seq=seq),1)
        self.g.update(self.link,msg('MISSION_ACK',type=13,mission_type=0),1)
        self.assertTrue(self.status['mission_active'])
        self.link.set_mode_apm.assert_not_called()
        self.upload()
        self.link.set_mode_apm.assert_called_with('AUTO')

    def test_float_request_is_answered_with_integer_item(self):
        self.g.update(self.link,msg('MISSION_REQUEST',seq=1),1)
        self.link.mav.mission_item_send.assert_not_called()
        self.assertEqual(self.link.mav.mission_item_int_send.call_args.args[-3:],(490000000,340000000,200))

    def test_autopilot_aims_inside_credited_tolerance(self):
        self.g.mission['waypoints'][0].update(aim_radius_m=50,radius_m=100)
        self.g.update(self.link,msg('MISSION_REQUEST',seq=1),1)
        self.assertEqual(self.link.mav.mission_item_int_send.call_args.args[8],50)

    def test_sequential_credit_leaves_autopilot_on_its_route(self):
        self.upload();self.link.mav.mission_set_current_send.reset_mock()
        self.g.update(self.link,msg('GLOBAL_POSITION_INT',lat=490000000,lon=340000000,relative_alt=200000),3)
        self.assertEqual(self.status['mission_completed'],[0])
        self.g.update(self.link,msg('MISSION_CURRENT',seq=1),3.5)
        self.g.update(self.link,msg('MISSION_CURRENT',seq=1),4)
        self.link.mav.mission_set_current_send.assert_not_called()
        self.assertEqual(self.status['mission_missed'],0)

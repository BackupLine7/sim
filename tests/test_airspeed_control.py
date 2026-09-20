import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from sim_bridge.airspeed_control import AirspeedControl
from pymavlink import mavutil
class AirspeedTests(unittest.TestCase):
    def test_guided_waits_for_parameters_and_command_ack(self):
        status={'mode':'GUIDED','mission_active':True};link=Mock()
        control=AirspeedControl(status,5)
        control.request(link,108,{'minimum_speed_kmh':36,'maximum_speed_kmh':350},0)
        for name,value in [('AIRSPEED_MIN',10),('AIRSPEED_MAX',98),('AIRSPEED_CRUISE',30)]:
            control.update(link,SimpleNamespace(get_type=lambda:'PARAM_VALUE',param_id=name,param_value=value),1)
        self.assertTrue(status['speed_pending'])
        link.mav.command_long_send.assert_called_once()
        control.update(link,SimpleNamespace(get_type=lambda:'COMMAND_ACK',command=mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,result=0),2)
        self.assertEqual(status['target_airspeed_kmh'],108)
        self.assertTrue(status['mission_active'])
        self.assertFalse(status['speed_pending'])
    def test_unconfirmed_request_does_not_report_success(self):
        status={'mode':'LOITER'};control=AirspeedControl(status,5)
        control.request(Mock(),90,{'minimum_speed_kmh':36,'maximum_speed_kmh':108},0)
        control.update(Mock(),None,6)
        self.assertNotIn('target_airspeed_kmh',status)
        self.assertFalse(status['speed_pending'])

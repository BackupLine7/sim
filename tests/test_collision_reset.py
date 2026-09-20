import json
import unittest
from pathlib import Path
from sim_bridge.flight_session import FlightSession

class CollisionTests(unittest.TestCase):
    def setUp(self):
        self.session=FlightSession(json.loads((Path(__file__).resolve().parents[1]/'config/airfield.json').read_text(encoding='utf-8')))
        self.status=dict(connected=True,armed=True,mode='GUIDED')

    def pose(self,time,height,roll=0):
        return dict(sim_time_s=time,altitude_agl_m=height,altitude_asl_m=153+height,airspeed_kt=50,roll_deg=roll)

    def test_contact_after_flight_crashes_and_reset_clears_history(self):
        self.session.update(self.pose(1,30),self.status)
        self.assertEqual(self.session.update(self.pose(2,.3),self.status),'crashed')
        self.session.reset()
        self.assertFalse(self.session.has_flown)
        self.assertIsNone(self.session.previous_pose)

    def test_start_on_ground_does_not_trigger_collision(self):
        self.status.update(armed=False,prearm_ready=True)
        self.assertEqual(self.session.update(self.pose(20,.3),self.status),'ready')

    def test_gentle_autoland_allowed_but_hard_impact_detected(self):
        self.status['mode']='AUTOLAND'
        self.session.update(self.pose(1,30),self.status)
        self.session.update(self.pose(20,1),self.status)
        self.assertNotEqual(self.session.update(self.pose(21,.3),self.status),'crashed')
        self.session.update(self.pose(22,10),self.status)
        self.assertEqual(self.session.update(self.pose(23,.3),self.status),'crashed')

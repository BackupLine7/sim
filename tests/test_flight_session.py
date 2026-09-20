import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sim_bridge.flight_session import FlightSession,SessionRuntime
class SessionTests(unittest.TestCase):
 def setUp(self):
  self.settings=json.loads(Path('config/airfield.json').read_text(encoding='utf-8'))
  self.session=FlightSession(self.settings)
  self.status={'connected':True,'armed':False,'mode':'MANUAL','prearm_ready':True}
 def pose(self,height=0.4,speed=0,time=40):
  return {'altitude_agl_m':height,'airspeed_kt':speed,'sim_time_s':time}
 def test_ground_is_not_a_completed_landing(self):
  self.assertEqual(self.session.update(self.pose(),self.status),'ready')
  self.assertFalse(self.session.has_flown)
 def test_ready_waits_for_actual_prearm_checks(self):
  self.status['prearm_ready']=False
  self.assertEqual(self.session.update(self.pose(),self.status),'preparing')
 def test_complete_flight_and_stopped_disarm(self):
  self.status.update(armed=True,mode='TAKEOFF')
  self.assertEqual(self.session.update(self.pose(),self.status),'takeoff')
  self.assertEqual(self.session.update(self.pose(height=25,speed=40),self.status),'flight')
  self.status['mode']='AUTOLAND'
  self.assertEqual(self.session.update(self.pose(height=60,speed=30),self.status),'landing')
  self.session.update(self.pose(height=1,time=49),self.status)
  self.session.update(self.pose(time=50),self.status)
  self.assertNotEqual(self.session.phase,'landed','armed aircraft is not completed')
  self.status['armed']=False
  self.session.update(self.pose(time=51),self.status)
  self.assertEqual(self.session.phase,'landing')
  self.session.update(self.pose(time=55),self.status)
  self.assertEqual(self.session.phase,'landed')
  self.session.reset()
  self.assertFalse(self.session.has_flown)
  self.assertEqual(self.session.phase,'restarting')
 def test_motion_resets_stop_timer(self):
  self.status.update(armed=True,mode='AUTOLAND')
  self.session.update(self.pose(height=25),self.status)
  self.status['armed']=False
  self.session.update(self.pose(time=50),self.status)
  self.session.update(self.pose(speed=10,time=52),self.status)
  self.session.update(self.pose(time=54),self.status)
  self.assertEqual(self.session.phase,'landing')
 def test_crash_is_not_successful_landing(self):
  self.status['notice']='CRASH_DETECTED'
  self.assertEqual(self.session.update(self.pose(),self.status),'crashed')
if __name__=='__main__':unittest.main()

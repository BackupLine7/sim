"""Command boundary tests; no network or aircraft needed."""
import sys
import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sim_bridge.flight_control import FlightControl
from sim_bridge.fdm_receiver import FdmPoseProtocol

class FlightControlTests(unittest.TestCase):
    def setUp(self):
        self.control = FlightControl('tcp:127.0.0.1:5760')

    def test_unknown_and_malformed_commands_are_rejected(self):
        for message in [None, [], {'type':'command','action':'execute'}, {'type':'command','action':'stick','roll':float('nan'),'pitch':0,'throttle':.5}]:
            with self.assertRaises(ValueError): self.control.submit(message)

    def test_disconnected_commands_are_not_queued(self):
        with self.assertRaises(ValueError): self.control.submit({'type':'command','action':'takeoff'})
        self.assertTrue(self.control.commands.empty())

    def test_command_backlog_is_bounded(self):
        self.control.status['connected'] = True
        for _ in range(8): self.control.submit({'type':'command','action':'loiter'})
        with self.assertRaises(ValueError): self.control.submit({'type':'command','action':'loiter'})

    def test_latest_stick_replaces_previous_input(self):
        for roll in [-.5,.5]: self.control.submit({'type':'command','action':'stick','roll':roll,'pitch':0,'throttle':.65})
        self.assertEqual(self.control.rc[1], .5)
        self.assertTrue(self.control.commands.empty())

    def test_pose_rejects_nonfinite_and_converts_height(self):
        protocol=FdmPoseProtocol(lambda pose:None, 0, 179)
        self.assertIsNone(protocol._parse(b'0,inf,30,100,0,0,90,40,328'))
        pose=protocol._parse(b'0,50.45,30.52,100,0,0,90,40,328.0839895')
        self.assertEqual(pose['altitude_asl_m'],279)
        self.assertAlmostEqual(pose['altitude_agl_m'],100)

    def test_return_after_manual_input_is_not_overwritten_by_loiter(self):
        control=self.control
        control.status.update(connected=True, mode='FBWA')
        control.rc=(time.monotonic(), 0, 0, .65)
        modes=[]
        calls=[]
        class Link:
            target_system=1
            target_component=1
            mav=SimpleNamespace(rc_channels_override_send=lambda *args:calls.append(args))
            count=0
            def wait_heartbeat(self, **kwargs): return object()
            def recv_match(self, **kwargs):
                self.count+=1
                if self.count==2:
                    control.commands.put('return')
                    control.stop_event.set()
                return None
            def set_mode_apm(self, mode): modes.append(mode)
            def close(self): pass
        with patch('sim_bridge.flight_control.mavutil.mavlink_connection', return_value=Link()):
            control._run()
        self.assertEqual(modes, ['RTL'])
        self.assertEqual(calls[-1][2:6], (0,0,0,0))

if __name__ == '__main__': unittest.main()

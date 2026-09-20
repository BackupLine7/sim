from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from sim_bridge.f16_control_adapter import apply_external_controls


class F16ControlAdapterTests(unittest.TestCase):
    def test_aerodynamics_use_actuated_surface_and_external_yaw(self):
        source = Path(__file__).resolve().parents[1] / 'third_party/jsbsim/aircraft/f16/f16.xml'
        tree = ET.parse(source)
        apply_external_controls(tree)
        apply_external_controls(tree)
        roll = tree.find("flight_control/channel[@name='Roll']")
        control = roll.find("aerosurface_scale[@name='fcs/aileron-control']")
        self.assertEqual(control.findtext('input'), 'fcs/aileron-speed-compensated')
        self.assertEqual(control.findtext('output'), 'fcs/aileron-pos-rad')
        self.assertLess(list(roll).index(roll.find("scheduled_gain[@name='fcs/aileron-speed-compensated']")), list(roll).index(control))
        scheduler = tree.find("flight_control/channel[@name='Yaw']/summer[@name='fcs/yaw-scheduler']")
        self.assertEqual([item.text for item in scheduler.findall('input')], ['fcs/rudder-cmd-norm', 'fcs/yaw-trim-cmd-norm'])
        self.assertIsNotNone(tree.find("flight_control/channel[@name='Yaw']/kinematic[@name='fcs/rudder-position']"))

import unittest
from sim_bridge.flight_session import IMMEDIATE_CLIMB_IN_AUTO, training_parameters


class TrainingParametersTests(unittest.TestCase):
    def test_aircraft_and_preferences_override_airfield(self):
        result=training_parameters({'WP_LOITER_RAD':150,'TKOFF_ALT':100},{'parameters':{'WP_LOITER_RAD':3000}},{'TKOFF_ALT':120})
        self.assertEqual((result['WP_LOITER_RAD'],result['TKOFF_ALT']),(3000,120))

    def test_immediate_climb_is_added_without_dropping_other_options(self):
        result=training_parameters({},{'parameters':{'FLIGHT_OPTIONS':4}},{})
        self.assertEqual(result['FLIGHT_OPTIONS'],4|IMMEDIATE_CLIMB_IN_AUTO)

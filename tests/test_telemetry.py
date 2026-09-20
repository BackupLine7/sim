import unittest
from types import SimpleNamespace
from sim_bridge.telemetry import update_telemetry

class TelemetryTest(unittest.TestCase):
    def message(self, kind, **values):
        return SimpleNamespace(get_type=lambda:kind, **values)

    def test_coordinates_and_altitudes_have_explicit_units(self):
        status={}
        update_telemetry(status,self.message('GLOBAL_POSITION_INT',lat=495703140,lon=343801100,alt=153000,relative_alt=120000))
        self.assertEqual(status['telemetry']['latitude_deg'],49.570314)
        self.assertEqual(status['telemetry']['longitude_deg'],34.38011)
        self.assertEqual(status['telemetry']['altitude_msl_m'],153)
        self.assertEqual(status['telemetry']['altitude_home_m'],120)

    def test_unknown_values_are_not_displayed_as_measurements(self):
        status={}
        update_telemetry(status,self.message('SYS_STATUS',voltage_battery=65535,current_battery=-1,battery_remaining=-1))
        update_telemetry(status,self.message('GPS_RAW_INT',fix_type=3,satellites_visible=255,eph=65535))
        self.assertIsNone(status['telemetry']['battery_voltage_v'])
        self.assertIsNone(status['telemetry']['battery_current_a'])
        self.assertIsNone(status['telemetry']['battery_remaining_pct'])
        self.assertIsNone(status['telemetry']['satellites'])
        self.assertIsNone(status['telemetry']['hdop'])

    def test_message_groups_preserve_other_fields(self):
        status={'telemetry':{'latitude_deg':49}}
        update_telemetry(status,self.message('VFR_HUD',airspeed=30,groundspeed=32,climb=-2,throttle=80))
        self.assertEqual(status['telemetry']['latitude_deg'],49)
        self.assertEqual(status['telemetry']['climb_m_s'],-2)

    def test_servo_commands_mapping_and_zero_unavailable(self):
        status={}
        update_telemetry(status,self.message('SERVO_OUTPUT_RAW',port=0,servo1_raw=1500,servo2_raw=0))
        update_telemetry(status,self.message('PARAM_VALUE',param_id='SERVO1_FUNCTION',param_value=4))
        self.assertEqual(status['telemetry']['servo_1_pwm'],1500)
        self.assertEqual(status['telemetry']['servo_1_function'],4)
        self.assertIsNone(status['telemetry']['servo_2_pwm'])
        self.assertIn('servo_1_pwm',status['telemetry_updated_ms'])

    def test_unknown_battery_temperature_and_temperature_units(self):
        status={}
        update_telemetry(status,self.message('BATTERY_STATUS',id=0,temperature=32767,current_consumed=-1))
        self.assertIsNone(status['telemetry']['battery_temperature_c'])
        update_telemetry(status,self.message('SCALED_PRESSURE',temperature=2350,press_abs=1013.25))
        self.assertEqual(status['telemetry']['barometer_temperature_c'],23.5)

    def test_self_diagnostics_masks_preserved(self):
        status={}
        update_telemetry(status,self.message('SYS_STATUS',voltage_battery=12000,current_battery=0,battery_remaining=80,
            onboard_control_sensors_present=43,onboard_control_sensors_enabled=43,onboard_control_sensors_health=11))
        self.assertEqual(status['telemetry']['sensors_present'],43)
        self.assertEqual(status['telemetry']['sensors_enabled'],43)
        self.assertEqual(status['telemetry']['sensors_health'],11)
        self.assertIn('sensors_health',status['telemetry_updated_ms'])

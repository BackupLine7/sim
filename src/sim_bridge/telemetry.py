"""Display telemetry only; unknown MAVLink values remain unavailable."""
import math
import time
def update_telemetry(status, message):
    kind = message.get_type()
    values = {}
    if kind == 'GLOBAL_POSITION_INT':
        values = dict(latitude_deg=message.lat/1e7, longitude_deg=message.lon/1e7,
                      altitude_msl_m=message.alt/1000, altitude_home_m=message.relative_alt/1000)
    elif kind == 'VFR_HUD':
        values = dict(airspeed_m_s=message.airspeed, groundspeed_m_s=message.groundspeed,
                      climb_m_s=message.climb, throttle_pct=message.throttle)
    elif kind == 'GPS_RAW_INT':
        values = dict(gps_fix=message.fix_type, satellites=None if message.satellites_visible == 255 else message.satellites_visible,
                      hdop=None if message.eph == 65535 else message.eph/100)
    elif kind == 'SYS_STATUS':
        values = dict(battery_voltage_v=None if message.voltage_battery == 65535 else message.voltage_battery/1000,
                      battery_current_a=None if message.current_battery == -1 else message.current_battery/100,
                      battery_remaining_pct=None if message.battery_remaining == -1 else message.battery_remaining)
        values.update({f'sensors_{name}':getattr(message, f'onboard_control_sensors_{name}', None)
                       for name in ('present', 'enabled', 'health')})
    elif kind == 'SERVO_OUTPUT_RAW' and message.port == 0:
        values={f'servo_{i}_pwm':getattr(message,f'servo{i}_raw',None) or None for i in range(1,9)}
    elif kind == 'PARAM_VALUE':
        name=message.param_id.decode().rstrip('\0') if isinstance(message.param_id,bytes) else message.param_id
        if name.startswith('SERVO') and name.endswith('_FUNCTION'):
            channel=name[5:-9]
            if channel.isdigit():values={f'servo_{channel}_function':int(message.param_value)}
    elif kind == 'RPM':
        values=dict(engine_rpm=message.rpm1)
    elif kind == 'SCALED_PRESSURE':
        values=dict(barometer_temperature_c=message.temperature/100,pressure_hpa=message.press_abs)
    elif kind == 'ATTITUDE':
        values=dict(roll_deg=math.degrees(message.roll),pitch_deg=math.degrees(message.pitch),yaw_deg=math.degrees(message.yaw)%360)
    elif kind == 'BATTERY_STATUS' and message.id == 0:
        values=dict(battery_temperature_c=None if message.temperature==32767 else message.temperature/100,
                    consumed_mah=None if message.current_consumed<0 else message.current_consumed)
    if values:
        status.setdefault('telemetry', {}).update(values)
        status.setdefault('telemetry_updated_ms',{}).update({key:time.time()*1000 for key in values})

"""Single-owner MAVLink connection for one local SITL workstation."""
import math
import queue
import threading
import time
import traceback
import json
from sim_bridge.missions import MissionStore
from sim_bridge.auto_mission_guidance import AutoMissionGuidance
from sim_bridge.airspeed_control import AirspeedControl
from sim_bridge.telemetry import update_telemetry
from sim_bridge.preferences import PreferencesStore

from pymavlink import mavutil


class FlightControl:
    MODES = {'loiter': 'LOITER', 'return': 'RTL', 'manual': 'FBWA', 'land': 'AUTOLAND'}

    def __init__(self, endpoint, runtime=None):
        self.endpoint = endpoint
        self.runtime = runtime
        self.flight_session = None
        if runtime:
            from sim_bridge.flight_session import FlightSession
            self.flight_session = FlightSession(runtime.settings)
        self.commands = queue.Queue(maxsize=8)
        self.status = {'type': 'status', 'connected': False, 'mode': '—', 'armed': False}
        self.status.update(generation=0, restarting=False, phase='preparing', prearm_ready=False)
        if runtime:self.status['home']=[runtime.polygon['home_longitude_deg'],runtime.polygon['home_latitude_deg'],runtime.polygon['home_elevation_asl_m'],runtime.polygon['home_heading_deg']]
        self.rc = None
        self.guidance = None
        if runtime:
            navigation = json.loads((runtime.root / 'config/mission-navigation.json').read_text(encoding='utf-8'))
            self.guidance = AutoMissionGuidance(self.status, navigation['target_timeout_s'], navigation['loiter_radius_fraction'])
            self.guidance.recovery_settings = navigation.get('altitude_recovery')
        self.airspeed = AirspeedControl(self.status, navigation['target_timeout_s']) if runtime else None
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._run, daemon=True, name='mavlink-control')

    def start(self):
        self.worker.start()

    def close(self):
        self.stop_event.set()
        self.worker.join(timeout=4)

    def submit(self, message):
        if not isinstance(message, dict) or message.get('type') != 'command':
            raise ValueError('Неверный формат команды')
        action = message.get('action')
        if action == 'restart':
            if not self.runtime:
                raise ValueError('Рестарт недоступен в этом подключении')
            if self.status['restarting']:
                return
            if message.get('aircraft_id') is not None:
                from sim_bridge.aircraft_catalog import AircraftCatalog
                AircraftCatalog(self.runtime.root).activate(message['aircraft_id'])
            if message.get('start_id') is not None:
                from sim_bridge.start_locations import StartLocations
                StartLocations(self.runtime.root).activate(message['start_id'])
            self.status.update(restarting=True, connected=False, prearm_ready=False, phase='restarting', notice='Перезапуск самолёта на ВПП…', generation=self.status['generation']+1)
            self.flight_session.reset()
            if self.guidance:
                self.guidance.cancel()
                self.status.update(mission_id=None, mission_next=0, mission_complete=False)
            self.rc = None
            while not self.commands.empty():
                try: self.commands.get_nowait()
                except queue.Empty: break
            threading.Thread(target=self._restart, daemon=True, name='session-restart').start()
            return
        if self.status['restarting']:
            raise ValueError('Дождитесь рестарта самолёта')
        if self.runtime and action == 'takeoff' and self.status['phase'] not in ('ready', 'landed'):
            raise ValueError('Взлёт доступен после подготовки на ВПП')
        if self.runtime and action == 'land' and (not self.flight_session.has_flown or not self.status['armed']):
            raise ValueError('Посадка доступна только в полёте')
        if action == 'stick':
            values = [message.get(k) for k in ('roll', 'pitch', 'throttle')]
            if any(type(v) not in (float, int) or not math.isfinite(v) for v in values):
                raise ValueError('Некорректные значения управления')
            roll, pitch, throttle = values
            if not (-1 <= roll <= 1 and -1 <= pitch <= 1 and 0 <= throttle <= 1):
                raise ValueError('Управление вне диапазона')
            yaw=message.get('yaw',0)
            if type(yaw) not in (int,float) or not math.isfinite(yaw) or not -1<=yaw<=1:
                raise ValueError('Рыскание вне диапазона')
            self.rc = (time.monotonic(), roll, pitch, throttle,yaw)
            return
        if action == 'speed':
            if not self.runtime or self.status['mode'] not in AirspeedControl.MODES or self.status['phase'] != 'flight':
                raise ValueError('Задание скорости доступно в полёте на автопилоте')
            speed = message.get('speed_kmh')
            limits = PreferencesStore(self.runtime.root).read()['aircraft']
            if type(speed) not in (int,float) or not math.isfinite(speed) or not limits['minimum_speed_kmh'] <= speed <= limits['maximum_speed_kmh']:
                raise ValueError('Скорость вне заданных в настройках пределов')
            action = ('speed', speed, limits)
        if action == 'mission_check':
            index, checked = message.get('index'), message.get('checked')
            mission = self.guidance.mission if self.guidance else None
            if not mission or message.get('mission_id') != mission['id'] or type(index) is not int or not 0 <= index < len(mission['waypoints']) or type(checked) is not bool:
                raise ValueError('Точка активной миссии не найдена')
            action = ('mission_check', index, checked, mission['id'])
        if action == 'mission':
            if not self.runtime or self.status['phase'] != 'flight' or not self.status['armed']:
                raise ValueError('Следование маршруту доступно после взлёта')
            mission = next((item for item in MissionStore.catalog(self.runtime.root)['missions'] if item['id'] == message.get('mission_id')), None)
            if mission is None:
                raise ValueError('Выберите существующую миссию')
            from .mission_terrain import prepare_terrain_mission
            mission=prepare_terrain_mission(self.runtime,mission,self.status.get('telemetry',{}))
            completed = message.get('completed', [])
            if not isinstance(completed,list) or any(type(i) is not int or not 0 <= i < len(mission['waypoints']) for i in completed):
                raise ValueError('Некорректные отметки точек')
            action = ('mission', mission, completed)
        if not isinstance(action, tuple) and action not in (*self.MODES, 'takeoff', 'release'):
            raise ValueError('Неизвестная команда')
        if not self.status['connected']:
            raise ValueError('Автопилот не подключён')
        try:
            self.commands.put_nowait(action)
        except queue.Full:
            raise ValueError('Дождитесь выполнения предыдущей команды') from None

    def _run(self):
        while not self.stop_event.is_set():
            link = None
            try:
                link = mavutil.mavlink_connection(self.endpoint, source_system=255)
                if link.wait_heartbeat(timeout=3) is None:
                    raise TimeoutError('Нет heartbeat')
                self.status['connected'] = True
                self.status['telemetry']={}
                self.status['telemetry_updated_ms']={}
                if self.runtime:
                    for message_id in (36,30,29,147,226):
                        link.mav.command_long_send(link.target_system,link.target_component,mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,0,message_id,200000,0,0,0,0,0)
                    for channel in range(1,9):
                        link.mav.param_request_read_send(link.target_system,link.target_component,f'SERVO{channel}_FUNCTION'.encode(),-1)
                    link.mav.request_data_stream_send(link.target_system, link.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 2, 1)
                    link.mav.request_data_stream_send(link.target_system, link.target_component, mavutil.mavlink.MAV_DATA_STREAM_EXTRA2, 2, 1)
                    link.mav.request_data_stream_send(link.target_system, link.target_component, mavutil.mavlink.MAV_DATA_STREAM_POSITION, 5, 1)
                last_heartbeat = time.monotonic()
                last_rc = 0
                sent_rc = None
                had_rc = False
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    message = link.recv_match(blocking=True, timeout=0.03)
                    if message:
                        update_telemetry(self.status, message)
                        kind = message.get_type()
                        if kind == 'HEARTBEAT':
                            last_heartbeat = now
                            self.status.update(mode=mavutil.mode_string_v10(message), armed=bool(message.base_mode & 128))
                        elif kind == 'STATUSTEXT':
                            self.status['notice'] = message.text
                            events=self.status.setdefault('autopilot_events',[])
                            self.status['autopilot_event_id']=self.status.get('autopilot_event_id',0)+1
                            events.append(dict(id=self.status['autopilot_event_id'],text=message.text,severity=message.severity))
                            del events[:-100]
                        elif kind == 'COMMAND_ACK':
                            self.status['command_result'] = int(message.result)
                        elif kind == 'VFR_HUD':
                            self.status['ground_speed_m_s'] = float(message.groundspeed)
                            self.status['engine_throttle_pct'] = int(message.throttle)
                        elif kind == 'SYS_STATUS':
                            self.status['prearm_ready'] = bool(message.onboard_control_sensors_health & mavutil.mavlink.MAV_SYS_STATUS_PREARM_CHECK)
                    if now - last_heartbeat > 4:
                        raise TimeoutError('Потеряна связь с автопилотом')
                    try:
                        action = self.commands.get_nowait()
                    except queue.Empty:
                        action = None
                    if self.airspeed:
                        self.airspeed.update(link, message, now)
                    if isinstance(action, tuple) and action[0] == 'speed':
                        self.airspeed.request(link, action[1], action[2], now)
                        action = None
                    if isinstance(action, tuple) and action[0] == 'mission_check':
                        if self.guidance.mission and self.guidance.mission['id'] == action[3]:
                            self.guidance.check(link, action[1], action[2], now)
                        action = None
                        message = None
                    if action and self.guidance:
                        self.guidance.cancel()
                    if isinstance(action, tuple):
                        self.rc = None
                        if had_rc:
                            link.mav.rc_channels_override_send(link.target_system, link.target_component, 0, 0, 0, 0, 65535, 65535, 65535, 65535)
                            had_rc = False
                        # The route uses the aircraft's own bank limit: a lower cap multiplies
                        # the turn radius (F-16 at 600 km/h: 4.9 km at 30 deg, 1.3 km at 65 deg).
                        bank = PreferencesStore(self.runtime.root).read()['aircraft']['maximum_bank_deg']
                        link.mav.param_set_send(link.target_system,link.target_component,b'ROLL_LIMIT_DEG',bank,mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
                        self.guidance.start(link, action[1], now, action[2])
                        action = None
                        message = None
                    if self.guidance:
                        self.guidance.update(link, message, now)
                    if action == 'takeoff':
                        if self.runtime:
                            limits=PreferencesStore(self.runtime.root).read()['aircraft']
                            bank=limits['maximum_bank_deg']
                            speed=max(self.status.get('ground_speed_m_s',0),limits['cruise_speed_kmh']/3.6)
                            radius=speed*speed/(9.80665*math.tan(math.radians(bank)))
                            for name,value in [('ROLL_LIMIT_DEG',bank),('WP_LOITER_RAD',radius)]:
                                link.mav.param_set_send(link.target_system,link.target_component,name.encode(),value,mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
                        # Demo-only defaults. Training scenarios retain their own checks.
                        takeoff_altitude = self.runtime.settings['takeoff_altitude_m'] if self.runtime else 150
                        if self.runtime:
                            from sim_bridge.takeoff_terrain import plan_takeoff
                            try:
                                takeoff_altitude=plan_takeoff(self.runtime)
                            except ValueError as error:
                                self.status['notice']=str(error)
                                continue
                            self.status['takeoff_target_relative_m']=takeoff_altitude
                            self.status['notice']=f'Взлёт с учётом рельефа: набор до {takeoff_altitude:.0f} м над стартом'
                        for name, value in [('TKOFF_THR_MINACC', 0), ('TKOFF_THR_MINSPD', 0), ('TKOFF_ALT', takeoff_altitude), ('THR_FAILSAFE', 0)]:
                            link.mav.param_set_send(link.target_system, link.target_component, name.encode(), value, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
                        link.set_mode_apm('TAKEOFF')
                        self.stop_event.wait(0.3)
                        link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
                    elif action in self.MODES:
                        if action == 'manual' and self.runtime:
                            bank=PreferencesStore(self.runtime.root).read()['aircraft']['maximum_bank_deg']
                            link.mav.param_set_send(link.target_system,link.target_component,b'ROLL_LIMIT_DEG',bank,mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
                        self.rc = None
                        # Release overrides before selecting the requested mode. Otherwise
                        # the stale-input guard would overwrite RTL with LOITER below.
                        if had_rc:
                            link.mav.rc_channels_override_send(link.target_system, link.target_component, 0, 0, 0, 0, 65535, 65535, 65535, 65535)
                            had_rc = False
                        link.set_mode_apm(self.MODES[action])
                    elif action == 'release':
                        self.rc = None
                        if self.status['mode'] == 'FBWA':
                            link.set_mode_apm('LOITER')
                    rc = self.rc
                    if rc is not sent_rc or now - last_rc >= 0.1:
                        last_rc = now
                        sent_rc = rc
                        if rc and now - rc[0] < 0.7 and self.status['mode'] == 'FBWA':
                            _, roll, pitch, throttle = rc[:4]
                            yaw=rc[4] if len(rc)>4 else 0
                            link.mav.rc_channels_override_send(link.target_system, link.target_component, int(1500+400*roll), int(1500-400*pitch), int(1000+1000*throttle), int(1500+400*yaw), 65535, 65535, 65535, 65535)
                            had_rc = True
                        elif had_rc:
                            link.mav.rc_channels_override_send(link.target_system, link.target_component, 0, 0, 0, 0, 65535, 65535, 65535, 65535)
                            link.set_mode_apm('LOITER')
                            had_rc = False
            except Exception as error:
                if not isinstance(error, (OSError, TimeoutError)):
                    # A crash here would silently end the worker: submit() keeps
                    # accepting commands that nothing executes. Report and reconnect.
                    traceback.print_exc()
                if self.guidance:
                    self.guidance.cancel()
                self.status.update(connected=False, notice=str(error))
                self.rc = None
                while not self.commands.empty():
                    try:
                        self.commands.get_nowait()
                    except queue.Empty:
                        break
                self.stop_event.wait(1)
            finally:
                if link:
                    link.close()

    def _restart(self):
        try:
            self.runtime.restart()
            p=self.runtime.polygon
            self.status['home']=[p['home_longitude_deg'],p['home_latitude_deg'],p['home_elevation_asl_m'],p['home_heading_deg']]
            self.flight_session.phase = 'preparing'
            self.status.update(phase='preparing', notice='Подготовка самолёта на ВПП…', armed=False)
            deadline = time.monotonic() + self.runtime.settings['ready_timeout_s']
            while self.status['phase'] != 'ready':
                if time.monotonic() > deadline:
                    raise TimeoutError('Автопилот не подтвердил готовность за отведённое время')
                if self.stop_event.wait(0.1):
                    return
        except Exception as error:
            self.flight_session.phase = 'error'
            self.status.update(phase='error', notice=f'Ошибка рестарта: {error}')
        finally:
            self.status['restarting'] = False

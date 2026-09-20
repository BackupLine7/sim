"""Sequential GUIDED targets; all MAVLink calls stay on the control worker."""
import math
from pymavlink import mavutil


class MissionGuidance:
    def __init__(self, status, target_timeout_s, loiter_radius_fraction):
        self.status = status
        self.target_timeout_s = target_timeout_s
        self.loiter_radius_fraction = loiter_radius_fraction
        self.mission = None
        self.pending_at = None
        self.next = 0
        self.recovery_settings = None
        self.recovering = False
        self.settled_since = None
        self.flythrough_settings = None
        self.approach_bearing = None

    def cancel(self):
        self.mission = None
        self.pending_at = None
        self.status['mission_active'] = False
        self.status['mission_recovering'] = False

    def start(self, link, mission, now, completed=()):
        self.mission = mission
        self.completed = set(completed)
        self.next = next((i for i in range(len(mission['waypoints'])) if i not in self.completed), len(mission['waypoints']))
        self.status.update(mission_id=mission['id'], mission_next=0, mission_active=True, mission_complete=False, mission_end=None)
        if 'terrain_minimum_relative_m' in mission:
            self.status['notice']=f"Маршрут с учётом рельефа: не ниже {mission['terrain_minimum_relative_m']:.0f} м над стартом"
        self.publish_progress()
        if self.next == len(mission['waypoints']):
            self.cancel()
            self.status.update(mission_complete=True, mission_end='transit')
            link.set_mode_apm('LOITER')
            return
        self.send_target(link, now)

    def publish_progress(self):
        self.status.update(mission_next=self.next, mission_completed=sorted(self.completed))

    def check(self, link, index, checked, now):
        if not self.mission: return
        if checked: self.completed.add(index)
        else: self.completed.discard(index)
        previous = self.next
        self.next = next((i for i in range(len(self.mission['waypoints'])) if i not in self.completed), len(self.mission['waypoints']))
        self.publish_progress()
        if self.next == len(self.mission['waypoints']):
            self.cancel()
            self.status.update(mission_complete=True, mission_end='transit')
            link.set_mode_apm('LOITER')
        elif self.next != previous:
            self.send_target(link, now)

    def send_target(self, link, now):
        self.recovering = False
        self.status['mission_recovering'] = False
        point = self.mission['waypoints'][self.next]
        latitude,longitude=point['latitude_deg'],point['longitude_deg']
        self.approach_bearing=None
        if self.flythrough_settings:
            telemetry=self.status.get('telemetry',{})
            origin_lat=telemetry.get('latitude_deg')
            origin_lon=telemetry.get('longitude_deg')
            if origin_lat is not None and origin_lon is not None:
                # GUIDED circles its destination. Put that destination beyond the
                # acceptance point so the approach crosses the point before turning.
                settings=self.flythrough_settings
                lat1,lat2=map(math.radians,(origin_lat,latitude))
                delta=math.radians(longitude-origin_lon)
                bearing=math.atan2(math.sin(delta)*math.cos(lat2),math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(delta))
                self.approach_bearing=bearing
                speed=max(telemetry.get('groundspeed_m_s',0),telemetry.get('airspeed_m_s',0))
                turn_radius=speed**2/(9.80665*math.tan(math.radians(settings['bank_deg'])))
                angular=max(settings['minimum_extension_m'],settings['turn_radius_factor']*turn_radius,point['radius_m']*2)/6378137
                target_lat=math.asin(math.sin(lat2)*math.cos(angular)+math.cos(lat2)*math.sin(angular)*math.cos(bearing))
                target_lon=math.radians(longitude)+math.atan2(math.sin(bearing)*math.sin(angular)*math.cos(lat2),math.cos(angular)-math.sin(lat2)*math.sin(target_lat))
                latitude,longitude=math.degrees(target_lat),(math.degrees(target_lon)+180)%360-180
        # A smaller holding circle lets the aircraft enter the acceptance region
        # even when it needs another circuit to reach the requested altitude.
        link.mav.command_int_send(
            link.target_system, link.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            mavutil.mavlink.MAV_CMD_DO_REPOSITION, 0, 0,
            -1, mavutil.mavlink.MAV_DO_REPOSITION_FLAGS_CHANGE_MODE,
            point['radius_m'] * self.loiter_radius_fraction, 0,
            round(latitude * 1e7), round(longitude * 1e7),
            point['altitude_relative_m'])
        self.pending_at = now

    def update(self, link, message, now):
        if not self.mission:
            return
        if self.pending_at is not None and now - self.pending_at > self.target_timeout_s:
            self.cancel()
            link.set_mode_apm('LOITER')
            self.status['notice'] = 'Автопилот не подтвердил точку. Включён круг.'
            return
        if message is None:
            return
        if message.get_type() == 'COMMAND_ACK' and message.command == mavutil.mavlink.MAV_CMD_DO_REPOSITION and self.pending_at is not None:
            if message.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                self.cancel()
                link.set_mode_apm('LOITER')
                self.status['notice'] = 'Автопилот отклонил точку. Включён круг.'
            else:
                self.pending_at = None
            return
        if message.get_type() == 'HEARTBEAT' and self.pending_at is None and self.status['mode'] != 'GUIDED':
            self.cancel()
            return
        if message.get_type() != 'GLOBAL_POSITION_INT' or self.pending_at is not None or self.status['mode'] != 'GUIDED':
            return
        point = self.mission['waypoints'][self.next]
        latitude_rad = math.radians(message.lat / 1e7)
        target_latitude_rad = math.radians(point['latitude_deg'])
        delta_longitude_rad = math.radians(message.lon / 1e7 - point['longitude_deg'])
        haversine = math.sin((latitude_rad-target_latitude_rad)/2)**2 + math.cos(latitude_rad)*math.cos(target_latitude_rad)*math.sin(delta_longitude_rad/2)**2
        distance_m = 2 * 6378137.0 * math.asin(math.sqrt(min(1, max(0, haversine))))
        height_error = abs(message.relative_alt/1000-point['altitude_relative_m'])
        if self.recovering:
            stable = height_error <= self.mission['height_tolerance_m'] and abs(self.status.get('telemetry',{}).get('climb_m_s',0)) <= self.recovery_settings.get('settled_climb_m_s',2)
            if not stable: self.settled_since = None
            elif self.settled_since is None: self.settled_since = now
            if stable and now-self.settled_since >= self.recovery_settings.get('settled_duration_s',0):
                self.status['notice']='Высота выровнена. Повторный заход на точку'
                self.send_target(link, now)
            return
        if self.recovery_settings and height_error > self.mission['height_tolerance_m']:
            settings = self.recovery_settings
            speed = max(0,self.status.get('telemetry',{}).get('groundspeed_m_s',0))
            approach = speed*(height_error/settings['vertical_speed_m_s']+settings['approach_margin_s'])
            if distance_m <= max(point['radius_m'],approach) and speed > 0:
                # Put the holding centre to the right of the velocity vector:
                # the aircraft starts tangent to the circle, not at its centre.
                radius = speed*speed/(9.80665*math.tan(math.radians(settings['bank_deg'])))
                heading = math.atan2(getattr(message,'vy',0),getattr(message,'vx',0))
                if not getattr(message,'vx',0) and not getattr(message,'vy',0):
                    heading = math.radians(self.status.get('telemetry',{}).get('yaw_deg',0))
                lat = message.lat/1e7-math.sin(heading)*radius/111320
                lon = message.lon/1e7+math.cos(heading)*radius/(111320*max(.01,math.cos(latitude_rad)))
                link.mav.command_int_send(link.target_system,link.target_component,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,mavutil.mavlink.MAV_CMD_DO_REPOSITION,0,0,
                    -1,mavutil.mavlink.MAV_DO_REPOSITION_FLAGS_CHANGE_MODE,radius,0,
                    round(lat*1e7),round(lon*1e7),point['altitude_relative_m'])
                self.recovering=True
                self.status['mission_recovering']=True
                self.settled_since=None
                self.pending_at=now
                self.status['notice']='Выравнивание высоты на круге перед повторным заходом на точку'
                return
        if distance_m > point['radius_m'] or abs(message.relative_alt/1000-point['altitude_relative_m']) > self.mission['height_tolerance_m']:
            if self.approach_bearing is not None:
                north=(message.lat/1e7-point['latitude_deg'])*111320
                east=(message.lon/1e7-point['longitude_deg'])*111320*math.cos(target_latitude_rad)
                passed=north*math.cos(self.approach_bearing)+east*math.sin(self.approach_bearing)
                if passed>point['radius_m']:
                    self.status['notice']='Точка не пройдена в допуске. Повторный заход.'
                    self.send_target(link,now)
            return
        self.completed.add(self.next)
        self.next = next((i for i in range(len(self.mission['waypoints'])) if i not in self.completed), len(self.mission['waypoints']))
        self.publish_progress()
        if self.next == len(self.mission['waypoints']):
            final_type = point.get('type', 'transit')
            self.cancel()
            self.status.update(mission_complete=True, mission_end=final_type)
            if final_type == 'land':
                link.set_mode_apm('AUTOLAND')
                self.status['notice'] = 'Маршрут пройден. Автопилот выполняет посадку на аэродроме.'
            elif final_type == 'goal':
                self.status['notice'] = 'Цель достигнута. Задание завершено.'
            else:
                link.set_mode_apm('LOITER')
                self.status['notice'] = 'Маршрут завершён. Ожидание: самолёт выполняет круги.'
        else:
            self.send_target(link, now)

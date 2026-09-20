"""AUTO waypoint upload and position-based acceptance on the MAVLink worker."""
import math
from pymavlink import mavutil
from .mission_guidance import MissionGuidance
from .waypoint_crossing import crosses_waypoint

M=mavutil.mavlink


class AutoMissionGuidance(MissionGuidance):
    def start(self, link, mission, now, completed=()):
        self.uploading=True
        self.mode_pending=False
        self.requested=set()
        self.ahead_reports=0
        self.previous_position=None
        self.status['mission_missed']=0
        super().start(link,mission,now,completed)
        self.status['mission_waypoints']=mission['waypoints']

    def send_target(self, link, now):
        self.previous_position=None
        self.ahead_reports=0
        if self.uploading:
            link.mav.mission_count_send(link.target_system,link.target_component,len(self.mission['waypoints'])+2)
        else:
            link.mav.mission_set_current_send(link.target_system,link.target_component,self.next+1)
        self.pending_at=now

    def fail(self, link, text):
        self.cancel();link.set_mode_apm('LOITER');self.status['notice']=text

    def update(self, link, message, now):
        if not self.mission:return
        if self.pending_at is not None and now-self.pending_at>self.target_timeout_s:
            self.fail(link,'AUTO: нет подтверждения маршрута. Включён круг.');return
        if message is None:return
        kind=message.get_type()
        points=self.mission['waypoints']
        if self.uploading:
            if kind in ('MISSION_REQUEST_INT','MISSION_REQUEST'):
                seq=message.seq
                if not 0<=seq<len(points)+2:return
                if seq==0:
                    home=self.status.get('home',[points[0]['longitude_deg'],points[0]['latitude_deg'],0])
                    lat,lon,alt=home[1],home[0],home[2]
                    command=M.MAV_CMD_NAV_WAYPOINT;frame=M.MAV_FRAME_GLOBAL_INT;radius=0
                else:
                    point=points[min(seq-1,len(points)-1)]
                    lat,lon,alt=point['latitude_deg'],point['longitude_deg'],point['altitude_relative_m']
                    command=M.MAV_CMD_NAV_WAYPOINT if seq<=len(points) else M.MAV_CMD_NAV_LOITER_UNLIM
                    frame=M.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
                    # Explicit acceptance avoids L1's speed-dependent early turn. The
                    # autopilot switches inside the smaller aim radius, so the position
                    # samples have already entered the credited tolerance cylinder.
                    radius=min(255,point.get('aim_radius_m',point['radius_m']))
                # ArduPlane 4.7 asks with MISSION_REQUEST but warns about float items.
                link.mav.mission_item_int_send(link.target_system,link.target_component,seq,frame,command,0,1,0,radius,0,0,round(lat*1e7),round(lon*1e7),alt)
                self.requested.add(seq);self.pending_at=now
            elif kind=='MISSION_ACK':
                if getattr(message,'mission_type',M.MAV_MISSION_TYPE_MISSION)!=M.MAV_MISSION_TYPE_MISSION:return
                if message.type==M.MAV_MISSION_INVALID_SEQUENCE:
                    # A repeated request is answered twice; the late copy is refused
                    # and ArduPilot simply asks again for the item it still needs.
                    return
                if message.type!=M.MAV_MISSION_ACCEPTED:
                    self.fail(link,'Автопилот отклонил загрузку AUTO-маршрута.');return
                if len(self.requested)!=len(points)+2:return
                self.uploading=False;self.mode_pending=True
                self.send_target(link,now)
                link.set_mode_apm('AUTO')
                self.status['notice']='Маршрут передан: AUTO, пролёт через точки.'
            return
        if kind=='HEARTBEAT':
            if self.status['mode']=='AUTO':self.mode_pending=False
            elif not self.mode_pending:self.cancel()
            return
        if kind=='MISSION_CURRENT':
            if message.seq==self.next+1:
                self.pending_at=None;self.ahead_reports=0
            elif message.seq<=self.next:
                # Still flying to a point already credited at the tolerance edge:
                # ArduPlane switches itself at the aim radius or the finish line.
                self.ahead_reports=0
            elif not self.mode_pending:
                # ArduPlane can advance after crossing the finish line outside
                # the acceptance cylinder. Never count that as a reached point.
                # The first report may precede the position sample that crosses the
                # cylinder, so only a repeated report means the point was missed.
                self.ahead_reports+=1
                if self.ahead_reports>=2:
                    self.status['mission_missed']=self.status.get('mission_missed',0)+1
                    self.status['notice']='Точка пройдена вне допуска. Повторный заход.'
                    self.send_target(link,now)
            return
        if kind!='GLOBAL_POSITION_INT' or self.status['mode']!='AUTO':return
        point=points[self.next]
        current=(message.lat/1e7,message.lon/1e7,message.relative_alt/1000)
        previous=self.previous_position
        self.previous_position=(now,current)
        crossed=previous is not None and 0<now-previous[0]<=1 and crosses_waypoint(previous[1],current,point,self.mission['height_tolerance_m'])
        a,b=math.radians(message.lat/1e7),math.radians(point['latitude_deg'])
        d=math.radians(message.lon/1e7-point['longitude_deg'])
        h=math.sin((a-b)/2)**2+math.cos(a)*math.cos(b)*math.sin(d/2)**2
        distance=2*6378137*math.asin(math.sqrt(min(1,max(0,h))))
        if not crossed and (distance>point['radius_m'] or abs(message.relative_alt/1000-point['altitude_relative_m'])>self.mission['height_tolerance_m']):return
        credited=self.next
        self.completed.add(credited)
        self.next=next((i for i in range(len(points)) if i not in self.completed),len(points))
        self.publish_progress()
        if self.next<len(points):
            self.previous_position=None
            # Sequential credit leaves the autopilot on its route. Only a skipped
            # (manually checked) point needs an explicit retarget.
            if self.next!=credited+1:self.send_target(link,now)
            return
        final_type=point.get('type','transit')
        self.cancel();self.status.update(mission_complete=True,mission_end=final_type)
        if final_type=='land':link.set_mode_apm('AUTOLAND')
        elif final_type!='goal':link.set_mode_apm('LOITER')
        self.status['notice']='Маршрут пройден.'

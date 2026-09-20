"""Confirmed airspeed requests without changing flight mode or mission."""
import math
from pymavlink import mavutil

class AirspeedControl:
    MODES={'GUIDED','AUTO','LOITER','RTL','TAKEOFF','CRUISE','FBWB'}
    def __init__(self,status,timeout_s):
        self.status=status;self.timeout_s=timeout_s;self.pending=None

    def request(self,link,speed_kmh,limits,now):
        self.pending={'AIRSPEED_MIN':math.floor(limits['minimum_speed_kmh']/3.6),'AIRSPEED_MAX':math.ceil(limits['maximum_speed_kmh']/3.6),'AIRSPEED_CRUISE':speed_kmh/3.6}
        self.speed_kmh=speed_kmh;self.started=now;self.awaiting_command=False
        self.status.update(speed_pending=True,notice='Передаём заданную воздушную скорость…')
        for name,value in self.pending.items():
            link.mav.param_set_send(link.target_system,link.target_component,name.encode(),value,mavutil.mavlink.MAV_PARAM_TYPE_REAL32)

    def update(self,link,message,now):
        if self.pending is None:return
        if now-self.started>self.timeout_s:
            self.finish('Автопилот не подтвердил изменение скорости');return
        if message is None:return
        if message.get_type()=='PARAM_VALUE':
            name=message.param_id
            if isinstance(name,bytes):name=name.decode().rstrip('\0')
            if name in self.pending and math.isclose(message.param_value,self.pending[name],rel_tol=1e-5,abs_tol=.001):self.pending.pop(name)
            if not self.pending and not self.awaiting_command:
                if self.status['mode'] in ('GUIDED','AUTO'):
                    self.awaiting_command=True
                    link.mav.command_long_send(link.target_system,link.target_component,mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,0,0,self.speed_kmh/3.6,-1,0,0,0,0)
                else:self.accept()
        elif message.get_type()=='COMMAND_ACK' and self.awaiting_command and message.command==mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED:
            if message.result==mavutil.mavlink.MAV_RESULT_ACCEPTED:self.accept()
            else:self.finish('Автопилот отклонил заданную скорость')

    def accept(self):
        self.status['target_airspeed_kmh']=self.speed_kmh
        self.finish(f'Задана воздушная скорость {self.speed_kmh:g} км/ч')

    def finish(self,notice):
        self.pending=None;self.status.update(speed_pending=False,notice=notice)

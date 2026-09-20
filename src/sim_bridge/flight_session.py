"""Lifecycle of the single local training instance; never touches other containers."""
import json
import subprocess
from pathlib import Path
import yaml

# ArduPlane FLIGHT_OPTIONS bit IMMEDIATE_CLIMB_IN_AUTO. Without it AUTO spreads the
# climb over the whole leg, while mission_terrain assumes the route height from the
# start of the leg: a 136 km leg would reach its terrain clearance only at the end.
IMMEDIATE_CLIMB_IN_AUTO=1<<14


def training_parameters(airfield_parameters, aircraft, preference_parameters):
    parameters=dict(airfield_parameters)
    parameters.update(aircraft.get('parameters', {}))
    parameters.update(preference_parameters)
    parameters['FLIGHT_OPTIONS']=int(parameters.get('FLIGHT_OPTIONS',0))|IMMEDIATE_CLIMB_IN_AUTO
    return parameters


class SessionRuntime:
    def __init__(self, root):
        self.root=Path(root)
        self.settings=json.loads((self.root/'config/airfield.json').read_text(encoding='utf-8-sig'))
        self.polygon=yaml.safe_load((self.root/'config/simulation.yaml').read_text(encoding='utf-8'))['polygon']
        from dataclasses import asdict
        from sim_launcher.config import load_simulation_config
        self.polygon=asdict(load_simulation_config(self.root/'config/simulation.yaml').polygon)

    def prepare(self):
        from dataclasses import asdict
        from sim_launcher.config import load_simulation_config
        self.polygon=asdict(load_simulation_config(self.root/'config/simulation.yaml').polygon)
        self.settings.update(json.loads((self.root/"config/airfield.json").read_text(encoding="utf-8-sig")))
        from sim_bridge.start_locations import StartLocations
        starts=StartLocations(self.root)
        if starts.active_path.exists():
            location=json.loads(starts.active_path.read_text(encoding='utf-8'))
            if location['id']!='default':self.settings['name']=location['name']+' · учебная ВПП'
        from sim_bridge.aircraft_catalog import AircraftCatalog
        catalog=AircraftCatalog(self.root)
        aircraft=catalog.selected()
        catalog.prepare(aircraft)
        from sim_bridge.airframe_adapter import TrainingAirframeAdapter
        if aircraft['id']=='rascal':TrainingAirframeAdapter().apply(self.root/'build/jsbsim_root/instance-0/aircraft/Rascal/Rascal.xml',self.settings)
        directory=self.root/'build/sessions/0'
        directory.mkdir(parents=True,exist_ok=True)
        from sim_bridge.preferences import PreferencesStore
        preferences=PreferencesStore(self.root)
        parameters=training_parameters(self.settings['parameters'],aircraft,preferences.parameters())
        self.settings['takeoff_altitude_m']=parameters['TKOFF_ALT']
        (directory/'training.parm').write_text('\n'.join(f'{name} {value}' for name,value in parameters.items())+'\n',encoding='ascii')
        home=','.join(str(self.polygon[key]) for key in ['home_latitude_deg','home_longitude_deg','home_elevation_asl_m','home_heading_deg'])
        command='install -m 0755 /workspace/scripts/jsbsim_aircraft_wrapper.py /usr/local/bin/JSBSim\nexport FLIGHTLAB_JSBSIM_BINARY=/workspace/build/jsbsim-linux/src/JSBSim\n'
        command+=f"exec /workspace/third_party/ardupilot/build/sitl/bin/arduplane --wipe --model jsbsim:{aircraft['model']} --autotest-dir /workspace/build/jsbsim_root/instance-0 --home {home} --instance 0 --serial0 tcp:0 --speedup 1 --defaults /workspace/third_party/ardupilot/Tools/autotest/default_params/plane-jsbsim.parm,/workspace/build/sessions/0/training.parm\n"
        (directory/'launch.sh').write_text(command,encoding='ascii',newline='\n')
        session={'aircraft_id':aircraft['id'],'aircraft_name':aircraft['name'],'home':[self.polygon['home_longitude_deg'],self.polygon['home_latitude_deg']], 'ground_m':self.polygon['home_elevation_asl_m'], 'heading_deg':self.polygon['home_heading_deg'], 'airfield':self.settings, 'geoid_separation_m':load_simulation_config(self.root/'config/simulation.yaml').terrain.geoid_separation_m}
        (self.root/'web/data/session.json').write_text(json.dumps(session,ensure_ascii=False),encoding='utf-8')

    def restart(self):
        self.prepare()
        result=subprocess.run(['docker','restart',self.settings['container_name']],capture_output=True,text=True,timeout=self.settings['restart_timeout_s'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:
            raise OSError(result.stderr.strip() or 'Не удалось перезапустить SITL')

    def physics_failed(self):
        try:
            result=subprocess.run(['docker','inspect','--format','{{json .State}}',self.settings['container_name']],capture_output=True,text=True,timeout=self.settings['restart_timeout_s'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:
            return False
        if result.returncode:return False
        state=json.loads(result.stdout)
        return state.get('Status')=='exited' and state.get('ExitCode',0)!=0

class FlightSession:
    def __init__(self, settings):
        self.settings=settings
        self.phase='preparing'
        self.has_flown=False
        self.stopped_since=None
        self.previous_pose=None

    def reset(self):
        self.phase='restarting';self.has_flown=False;self.stopped_since=None
        self.previous_pose=None

    def update(self, pose, status):
        if self.phase in ('error','crashed'):
            return self.phase
        if not status.get('connected'):
            return self.phase
        height=pose['altitude_agl_m'];speed=status.get('ground_speed_m_s',pose['airspeed_kt']*0.514444)
        previous=self.previous_pose
        self.previous_pose=(pose['sim_time_s'],pose.get('altitude_asl_m',height))
        delta_s=pose['sim_time_s']-previous[0] if previous else 0
        sink_m_s=(previous[1]-pose.get('altitude_asl_m',height))/delta_s if delta_s>0 else 0
        if self.has_flown and height<=self.settings.get('collision_height_m',0.6):
            safe_landing=status.get('mode')=='AUTOLAND' and sink_m_s<=self.settings.get('safe_touchdown_sink_m_s',3) and abs(pose.get('roll_deg',0))<=self.settings.get('safe_touchdown_roll_deg',20)
            if not safe_landing:
                self.phase='crashed'
                return self.phase
        armed=status.get('armed',False)
        if 'CRASH' in status.get('notice','').upper():
            self.phase='crashed';return self.phase
        if height>self.settings['airborne_height_m']:
            self.has_flown=True
            self.phase='landing' if status.get('mode')=='AUTOLAND' else 'flight'
            self.stopped_since=None
        elif self.has_flown:
            if height<self.settings['ground_height_m'] and speed<self.settings['stopped_speed_m_s'] and not armed:
                if self.stopped_since is None:self.stopped_since=pose['sim_time_s']
                if pose['sim_time_s']-self.stopped_since>=self.settings['stopped_duration_s']:self.phase='landed'
            else:
                self.stopped_since=None
                if status.get('mode')=='AUTOLAND':self.phase='landing'
        elif status.get('mode')=='TAKEOFF' and armed:self.phase='takeoff'
        elif not armed and height<self.settings['ground_height_m']:
            self.phase='ready' if status.get('prearm_ready') and pose['sim_time_s']>=self.settings['startup_settle_s'] else 'preparing'
        return self.phase

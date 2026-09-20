"""Validated user settings; aircraft changes are applied only on session restart."""
import json
import math
from pathlib import Path

class PreferencesStore:
    SPEED_FIELDS={'minimum_speed_kmh','cruise_speed_kmh','maximum_speed_kmh','landing_speed_kmh'}
    LIMITS={'takeoff_altitude_m':(30,300),'return_altitude_m':(30,300),'maximum_bank_deg':(15,65),'wind_speed_m_s':(0,15),'wind_direction_deg':(0,359)}
    def __init__(self,root):self.root=Path(root)
    @property
    def path(self):
        model=self.aircraft_profile()
        suffix='.'+model['id'] if model and model['id']!='rascal' else ''
        return self.root/f'config/local.preferences{suffix}.json'
    def aircraft_profile(self):
        if not (self.root/'config/aircraft-catalog.json').exists():return None
        from sim_bridge.aircraft_catalog import AircraftCatalog
        return AircraftCatalog(self.root).selected()
    def envelope(self):
        model=self.aircraft_profile()
        if model:return {key:model[key] for key in ('model','maximum_commanded_airspeed_kmh','basis')}
        return json.loads((self.root/'config/aircraft-envelope.json').read_text(encoding='utf-8'))
    def read(self):
        path=self.path if self.path.exists() else self.root/'config/preferences.json'
        data=json.loads(path.read_text(encoding='utf-8-sig'));data.get('controls',{}).pop('layout',None)
        model=self.aircraft_profile()
        if model and not self.path.exists():
            for key,value in zip(('minimum_speed_kmh','cruise_speed_kmh','maximum_speed_kmh','landing_speed_kmh'),model['speeds']):data['aircraft'][key]=value
        limit=self.envelope()['maximum_commanded_airspeed_kmh']
        aircraft=data.get('aircraft',{})
        for key in self.SPEED_FIELDS:
            if type(aircraft.get(key)) in (int,float) and math.isfinite(aircraft[key]) and aircraft[key]>limit:aircraft[key]=limit
        if aircraft.get('minimum_speed_kmh',0)>=aircraft.get('cruise_speed_kmh',0):
            defaults=json.loads((self.root/'config/preferences.json').read_text(encoding='utf-8'))['aircraft']
            for key in self.SPEED_FIELDS:aircraft[key]=defaults[key]
        self.validate(data);return data
    def validate(self,data):
        if not isinstance(data,dict) or set(data)!= {'controls','aircraft'}:raise ValueError('Неверный формат настроек')
        controls=data['controls'];aircraft=data['aircraft']
        if not isinstance(controls,dict) or set(controls)!= {'invert_roll','invert_pitch','invert_yaw','roll_response','pitch_response','yaw_response'}:raise ValueError('Неверные настройки управления')
        for axis in ('roll','pitch','yaw'):
            if type(controls[f'invert_{axis}']) is not bool:raise ValueError('Инверсия должна быть включена или выключена')
            self.number(controls[f'{axis}_response'],.1,1)
        if not isinstance(aircraft,dict) or set(aircraft)!=set(self.LIMITS) | self.SPEED_FIELDS:raise ValueError('Неверные параметры самолёта')
        for name in self.SPEED_FIELDS:
            value=aircraft[name]
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError('Скорость должна быть положительным конечным числом')
            if value>self.envelope()['maximum_commanded_airspeed_kmh']:
                raise ValueError(f"Предел задания для {self.envelope()['model']}: {self.envelope()['maximum_commanded_airspeed_kmh']:g} км/ч")
        for name,(low,high) in self.LIMITS.items():self.number(aircraft[name],low,high)
        if not aircraft['minimum_speed_kmh']<aircraft['cruise_speed_kmh']<=aircraft['maximum_speed_kmh']:raise ValueError('Скорости должны идти по порядку: минимальная < крейсерская ≤ максимальная')
        if not aircraft['minimum_speed_kmh']<=aircraft['landing_speed_kmh']<=aircraft['cruise_speed_kmh']:raise ValueError('Посадочная скорость должна быть между минимальной и крейсерской')
    @staticmethod
    def number(value,low,high):
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError(f'Допустимое значение: {low}–{high}')
    def save(self,data):
        self.validate(data)
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(self.path)
    def parameters(self):
        data=self.read()['aircraft']
        return {'AIRSPEED_MIN':data['minimum_speed_kmh']/3.6,'AIRSPEED_CRUISE':data['cruise_speed_kmh']/3.6,'AIRSPEED_MAX':data['maximum_speed_kmh']/3.6,'TECS_LAND_ARSPD':data['landing_speed_kmh']/3.6,'TKOFF_ALT':data['takeoff_altitude_m'],'RTL_ALTITUDE':data['return_altitude_m'],'ROLL_LIMIT_DEG':data['maximum_bank_deg'],'SIM_WIND_SPD':data['wind_speed_m_s'],'SIM_WIND_DIR':data['wind_direction_deg']}

"""Conservative constant-height route clearance, not reactive obstacle avoidance."""
import math
from copy import deepcopy
from .world_elevation import SimulatorElevation
from sim_world.elevation.probe import elevation_probe


def cleared_mission(mission, origin, home_msl_m, settings, sample):
    result=deepcopy(mission)
    previous=origin
    highest=-math.inf
    for point in result['waypoints']:
        lat,lon=point['latitude_deg'],point['longitude_deg']
        middle=math.radians((lat+previous[0])/2)
        north=(lat-previous[0])*111320
        east=(lon-previous[1])*111320*max(.01,math.cos(middle))
        distance=math.hypot(north,east)
        steps=max(1,math.ceil(distance/settings['sample_step_m']))
        right_n=-east/max(distance,1);right_e=north/max(distance,1)
        for index in range(steps+1):
            fraction=index/steps
            for offset in (-settings['corridor_half_width_m'],0,settings['corridor_half_width_m']):
                sample_lat=previous[0]+(lat-previous[0])*fraction+right_n*offset/111320
                sample_lon=previous[1]+(lon-previous[1])*fraction+right_e*offset/(111320*max(.01,math.cos(middle)))
                value=sample(sample_lat,sample_lon)
                if not math.isfinite(value):raise ValueError('Нет высот для маршрута')
                highest=max(highest,value)
        previous=(lat,lon)
    minimum=highest+settings['clearance_m']-home_msl_m
    for point in result['waypoints']:
        if point.get('type') == 'goal':
            height=sample(point['latitude_deg'],point['longitude_deg'])
            if not math.isfinite(height):raise ValueError('Нет высоты ландшафта для цели')
            point['altitude_relative_m']=height-home_msl_m
            point['terrain_elevation_asl_m']=height
        else:
            point['altitude_relative_m']=max(point['altitude_relative_m'],minimum)
    result['terrain_minimum_relative_m']=minimum
    return result


def prepare_terrain_mission(runtime, mission, telemetry):
    import json
    navigation=json.loads((runtime.root/'config/mission-navigation.json').read_text())
    settings=navigation['terrain_clearance']
    world=SimulatorElevation(runtime.root)
    pending=set()
    def sample(lat,lon):
        value=elevation_probe(world,lat,lon)
        if not value['ready']:
            pending.add((math.floor(lat),math.floor(lon)))
            return 0
        return value['elevation_asl_m']
    origin=(telemetry.get('latitude_deg',runtime.polygon['home_latitude_deg']),telemetry.get('longitude_deg',runtime.polygon['home_longitude_deg']))
    result=cleared_mission(mission,origin,runtime.polygon['home_elevation_asl_m'],settings,sample)
    for point in result['waypoints']:
        # The autopilot aims at the radius the author drew; the multiplied radius is
        # the tolerance within which the pass is credited.
        point['aim_radius_m']=point['radius_m']
        point['radius_m']*=navigation['acceptance_radius_multiplier']
    if pending:
        raise ValueError(f'Подгружается рельеф маршрута ({len(pending)} участков). Повторите запуск миссии после загрузки.')
    return result

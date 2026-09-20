"""Terrain clearance target for the straight departure corridor, in MSL metres."""
import math
from .world_elevation import SimulatorElevation
from sim_world.elevation.probe import elevation_probe
from sim_world.elevation.streaming import tile_name


def departure_altitude(home, settings, elevation):
    heading=math.radians(home['home_heading_deg'])
    latitude=home['home_latitude_deg'];longitude=home['home_longitude_deg']
    highest=home['home_elevation_asl_m']
    for distance in range(0,settings['lookahead_m']+1,settings['sample_step_m']):
        for offset in (-settings['corridor_half_width_m'],0,settings['corridor_half_width_m']):
            north=math.cos(heading)*distance-math.sin(heading)*offset
            east=math.sin(heading)*distance+math.cos(heading)*offset
            lat=latitude+north/111320
            lon=longitude+east/(111320*math.cos(math.radians(latitude)))
            highest=max(highest,elevation(lat,lon))
    return highest+settings['clearance_m']-home['home_elevation_asl_m']


def plan_takeoff(runtime):
    world=SimulatorElevation(runtime.root)
    def sample(lat,lon):
        cache=world.cache
        if cache:
            with cache.lock:
                if tile_name(lat,lon) not in cache.tiles:
                    cache.request(lat,lon)
                    raise ValueError('Подгружается рельеф направления взлёта. Повторите взлёт после загрузки.')
        result=elevation_probe(world,lat,lon)
        if not result['ready']:raise ValueError('Подгружается рельеф направления взлёта. Повторите взлёт после загрузки.')
        return result['elevation_asl_m']
    settings=runtime.settings['takeoff_terrain']
    altitude=max(runtime.settings['takeoff_altitude_m'],departure_altitude(runtime.polygon,settings,sample))
    return altitude

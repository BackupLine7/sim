"""Prefetch imagery and OSM building footprints around a selected mission."""
import sys,json,urllib.request,urllib.parse,concurrent.futures
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sim_bridge.world import simulator_world
from sim_world import tile_xy, tile_bounds
from sim_world.vegetation.osm import height_m
mission=json.loads((ROOT/'config/missions/scenic-poltava.json').read_text(encoding='utf-8'))
store=simulator_world(ROOT)
z=store.settings['detail_level']
points=mission['waypoints'];keys=set()
for a,b in zip(points,points[1:]):
    for i in range(101):
        lon=a['longitude_deg']+(b['longitude_deg']-a['longitude_deg'])*i/100
        lat=a['latitude_deg']+(b['latitude_deg']-a['latitude_deg'])*i/100
        x,y=tile_xy(lon,lat,z)
        keys.update((z,x+dx,y+dy) for dx in range(-1,2) for dy in range(-1,2))
print('Imagery tiles',len(keys),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=store.settings['parallel_requests']) as pool:
    list(pool.map(lambda key:store.download(*key),sorted(keys)))
w=min(tile_bounds(*k)[0] for k in keys);s=min(tile_bounds(*k)[1] for k in keys)
e=max(tile_bounds(*k)[2] for k in keys);n=max(tile_bounds(*k)[3] for k in keys)
config=json.loads((ROOT/'config/osm-vegetation.json').read_text())
query=f'[out:json][timeout:{config["request_timeout_s"]}];way["building"]({s},{w},{n},{e});out body geom;'
req=urllib.request.Request(config['source_url'],data=urllib.parse.urlencode({'data':query}).encode(),headers={'User-Agent':'FlightLab-OfflineVegetation/1.0'})
with urllib.request.urlopen(req,timeout=config['request_timeout_s']+10) as response:data=json.load(response)
if data.get('remark'):raise ValueError(data['remark'])
buildings=[{'coordinates':[[p['lon'],p['lat']] for p in e['geometry']], 'height_m':height_m(e.get('tags',{}),store.settings['default_building_height_m'])} for e in data['elements'] if len(e.get('geometry',[]))>=4]
path=ROOT/store.settings['building_cache_path'];path.parent.mkdir(parents=True,exist_ok=True)
path.with_suffix('.tmp').write_text(json.dumps({'buildings':buildings,'credit':'OpenStreetMap contributors / ODbL','bounds':[w,s,e,n]}))
path.with_suffix('.tmp').replace(path)
print('Buildings',len(buildings),flush=True)

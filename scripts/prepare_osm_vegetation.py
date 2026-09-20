"""Download mapped tree rows/trees for current mission coverage before a session."""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sim_bridge.missions import MissionStore
from sim_world import tile_xy, tile_bounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Import an existing Overpass JSON response without network access')
    args = parser.parse_args()
    settings = json.loads((ROOT/'config/osm-vegetation.json').read_text(encoding='utf-8'))
    world = json.loads((ROOT/'config/world.json').read_text(encoding='utf-8'))
    points = [point for mission in MissionStore.catalog(ROOT)['missions'] for point in mission['waypoints']]
    tiles = [tile_xy(p['longitude_deg'],p['latitude_deg'],world['detail_level']) for p in points]
    radius = world['active_radius_tiles']
    west, _, _, north = tile_bounds(world['detail_level'],min(x for x,y in tiles)-radius,min(y for x,y in tiles)-radius)
    _, south, east, _ = tile_bounds(world['detail_level'],max(x for x,y in tiles)+radius,max(y for x,y in tiles)+radius)
    bounds = [west,south,east,north]
    if args.input:
        data = json.loads(args.input.read_text(encoding='utf-8'))
    else:
        bbox = f'{south},{west},{north},{east}'
        query = f'[out:json][timeout:{settings["request_timeout_s"]}];(way["natural"="tree_row"]({bbox});node["natural"="tree"]({bbox});way["highway"]({bbox}););out body geom;'
        request = urllib.request.Request(settings['source_url'],data=urllib.parse.urlencode({'data':query}).encode(),headers={'User-Agent':'FlightLab-OfflineVegetation/1.0'})
        print(f'Downloading OSM vegetation in {bounds}',flush=True)
        with urllib.request.urlopen(request,timeout=settings['request_timeout_s']+10) as response:
            data = json.load(response)
    if data.get('remark') or not isinstance(data.get('elements'),list):
        raise ValueError(f'Incomplete Overpass result: {data.get("remark", "missing elements")}')
    data.update(downloaded_at=datetime.now(timezone.utc).isoformat(),coverage_bounds=bounds,source=settings['source_url'],credit='© OpenStreetMap contributors · ODbL',license_url='https://www.openstreetmap.org/copyright')
    path = ROOT/settings['cache_path']
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)
    print(f'Saved {len(data["elements"])} mapped features to {path}',flush=True)


if __name__=='__main__':
    main()

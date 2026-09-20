"""Prefetch regional overview and selected detailed examples for offline use."""
import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sim_bridge.runway import read_polygon
from sim_bridge.world import simulator_world
from sim_world import tile_xy, tile_bounds

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detail',action='store_true',help='Download every regional tile at detail_level (large dataset).')
    args=parser.parse_args()
    store=simulator_world(ROOT)
    settings=store.settings
    west,south,east,north=settings['bounds']
    overview=settings['overview_level']
    x0,y0=tile_xy(west,north,overview)
    x1,y1=tile_xy(east,south,overview)
    keys={(overview,x,y) for x in range(x0,x1+1) for y in range(y0,y1+1)}
    detail=settings['detail_level']
    if args.detail:
        a,b=tile_xy(west,north,detail);c,d=tile_xy(east,south,detail)
        keys.update((detail,x,y) for x in range(a,c+1) for y in range(b,d+1))
    else:
        for lon,lat in [(30.5234,50.4501),(36.23,49.99),(35.045,48.465),(34.55,49.59),(37.58,48.735)]:
            x,y=tile_xy(lon,lat,detail)
            keys.update((detail,x+dx,y+dy) for dx in range(-1,2) for dy in range(-1,2))
    polygon=read_polygon(ROOT) if (ROOT/'config/simulation.yaml').exists() else None
    if polygon:
        x,y=tile_xy(polygon['home_longitude_deg'],polygon['home_latitude_deg'],detail)
        keys.update((detail,x+dx,y+dy) for dx in range(-2,3) for dy in range(-2,3))
    missing=[key for key in sorted(keys) if not store.path(*key).exists()]
    print(f'Prefetch: {len(missing)} missing / {len(keys)} tiles',flush=True)
    def fetch(key):
        try:
            store.download(*key)
            time.sleep(.35)
            return None
        except Exception as error:
            return f'{key}: {error}'
    errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings['parallel_requests']) as pool:
        for index,result in enumerate(pool.map(fetch,missing),1):
            if result: errors.append(result)
            if index%20==0: print(f'{index}/{len(missing)}; errors={len(errors)}',flush=True)
    if errors:
        print('\n'.join(errors[:15]),flush=True)
    overview_keys=[(overview,x,y) for x in range(x0,x1+1) for y in range(y0,y1+1)]
    if all(store.path(*key).exists() for key in overview_keys):
        mosaic=Image.new('RGB',((x1-x0+1)*256,(y1-y0+1)*256))
        for z,x,y in overview_keys:
            with Image.open(store.path(z,x,y)) as tile: mosaic.paste(tile,((x-x0)*256,(y-y0)*256))
        mosaic.save(ROOT/'web/data/east-overview.jpg',quality=88)
        a,b,c,d=tile_bounds(overview,x0,y0)
        e,f,g,h=tile_bounds(overview,x1,y1)
        (ROOT/'web/data/east-overview.json').write_text(json.dumps({'bounds':[a,f,g,d],'level':overview,'tiles':len(overview_keys)}))
    print(f'Completed: {len(keys)-len(errors)} cached; {len(errors)} failed',flush=True)
    return bool(errors)
if __name__=='__main__': raise SystemExit(main())

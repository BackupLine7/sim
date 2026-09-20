import math
import random
from collections import defaultdict
from .osm import EARTH_RADIUS_M, height_m


class PointIndex:
    def __init__(self, cell_m):
        self.cell_m = cell_m
        self.cells = defaultdict(list)

    def add(self, x, y, radius):
        self.cells[(math.floor(x/self.cell_m), math.floor(y/self.cell_m))].append((x,y,radius))

    def blocked(self, x, y):
        cx, cy = math.floor(x/self.cell_m), math.floor(y/self.cell_m)
        return any(math.hypot(x-a,y-b)<radius for dx in (-1,0,1) for dy in (-1,0,1)
                   for a,b,radius in self.cells.get((cx+dx,cy+dy),()))


class RoadsideVegetation:
    def __init__(self, elements, settings, mapped_trees, tile_key):
        self.by_tile = defaultdict(list)
        if not settings or not settings['enabled']:
            return
        for name in ('spacing_m','edge_clearance_m','default_road_width_m','junction_gap_m','mapped_tree_clearance_m','height_min_m','height_max_m'):
            if not math.isfinite(settings[name]) or settings[name]<=0:
                raise ValueError('Roadside parameters must be finite and positive')
        if settings['height_max_m']<settings['height_min_m']:
            raise ValueError('Invalid roadside height range')
        roads=[e for e in elements if e['type']=='way' and 'highway' in e.get('tags',{}) and len(e.get('geometry',[]))>1]
        if not roads:
            return
        lat0=math.radians(roads[0]['geometry'][0]['lat'])
        scale_x=EARTH_RADIUS_M*math.cos(lat0)*math.pi/180
        scale_y=EARTH_RADIUS_M*math.pi/180
        project=lambda p:(p['lon']*scale_x,p['lat']*scale_y)
        widths={e['id']:height_m({'height':e['tags'].get('width')},settings['default_road_width_m']) for e in roads}

        step_m=min(settings['edge_clearance_m']/2,settings['spacing_m']/2)
        max_radius=max(max(widths.values())/2+step_m,settings['mapped_tree_clearance_m'],settings['spacing_m']/2)
        blocked=PointIndex(max_radius)
        for lon,lat,_ in mapped_trees:
            blocked.add(lon*scale_x,lat*scale_y,settings['mapped_tree_clearance_m'])
        for road in roads:
            points=list(map(project,road['geometry']))
            for (ax,ay),(bx,by) in zip(points,points[1:]):
                count=max(1,math.ceil(math.hypot(bx-ax,by-ay)/step_m))
                for i in range(count+1):
                    blocked.add(ax+(bx-ax)*i/count,ay+(by-ay)*i/count,widths[road['id']]/2+step_m)
        for road in sorted(roads,key=lambda e:e['id']):
            tags=road['tags']
            if tags['highway'] not in settings['highway_types'] or any(tags.get(k,'no') not in ('no','0') for k in ('bridge','tunnel')):
                continue
            rng=random.Random(road['id']^settings['seed'])
            points=list(map(project,road['geometry']))
            lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
            total=sum(lengths)
            distance=settings['junction_gap_m']
            passed=0
            offset=widths[road['id']]/2+settings['edge_clearance_m']
            for (ax,ay),(bx,by),length in zip(points,points[1:],lengths):
                if not length:
                    continue
                while distance<=passed+length and distance<total-settings['junction_gap_m']:
                    t=(distance-passed)/length
                    for side in (-1,1):
                        x=ax+(bx-ax)*t-side*(by-ay)/length*offset
                        y=ay+(by-ay)*t+side*(bx-ax)/length*offset
                        height=rng.uniform(settings['height_min_m'],settings['height_max_m'])
                        if not blocked.blocked(x,y):
                            lon,lat=x/scale_x,y/scale_y
                            self.by_tile[tile_key(lon,lat)].append([lon,lat,height])
                            blocked.add(x,y,settings['spacing_m']/2)
                    distance+=settings['spacing_m']
                passed+=length

    def trees(self,x,y):
        return self.by_tile.get((x,y),[])
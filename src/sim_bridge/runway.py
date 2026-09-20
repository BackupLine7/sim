import json
import math
from pathlib import Path

METRES_PER_DEGREE_LATITUDE = 111320
TREE_CLEARANCE_ALONG_M = 20
TREE_CLEARANCE_ACROSS_M = 10


def runway_frame(polygon, latitude_deg, longitude_deg):
    heading_rad = math.radians(polygon['home_heading_deg'])
    north_m = (latitude_deg - polygon['home_latitude_deg']) * METRES_PER_DEGREE_LATITUDE
    east_m = (longitude_deg - polygon['home_longitude_deg']) * METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(latitude_deg))
    forward_m = north_m * math.cos(heading_rad) + east_m * math.sin(heading_rad)
    right_m = east_m * math.cos(heading_rad) - north_m * math.sin(heading_rad)
    return forward_m, right_m


def read_polygon(root):
    import yaml
    return yaml.safe_load((Path(root) / 'config/simulation.yaml').read_text(encoding='utf-8'))['polygon']


def read_airfield(root):
    return json.loads((Path(root) / 'config/airfield.json').read_text(encoding='utf-8-sig'))


class RunwayFootprint:
    def __init__(self, root):
        self.polygon = read_polygon(root)
        self.airfield = read_airfield(root)

    def __call__(self, longitude_deg, latitude_deg):
        forward_m, right_m = runway_frame(self.polygon, latitude_deg, longitude_deg)
        start_m = -self.airfield['start_from_threshold_m']
        along = start_m - TREE_CLEARANCE_ALONG_M < forward_m < start_m + self.airfield['runway_length_m'] + TREE_CLEARANCE_ALONG_M
        across = abs(right_m) < self.airfield['runway_width_m'] / 2 + TREE_CLEARANCE_ACROSS_M
        return along and across


class RunwaySurface:
    def __init__(self, polygon, airfield, blend_m):
        self.polygon = polygon
        self.airfield = airfield
        self.blend_m = blend_m

    def __call__(self, latitude_deg, longitude_deg, ground_asl_m):
        forward_m, right_m = runway_frame(self.polygon, latitude_deg, longitude_deg)
        start_m = -self.airfield['start_from_threshold_m']
        gap_m = math.hypot(
            max(start_m - forward_m, forward_m - start_m - self.airfield['runway_length_m'], 0),
            max(abs(right_m) - self.airfield['runway_width_m'] / 2, 0))
        blend = min(1, gap_m / self.blend_m)
        blend = blend * blend * (3 - 2 * blend)
        return self.polygon['home_elevation_asl_m'] * (1 - blend) + ground_asl_m * blend

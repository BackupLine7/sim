import math
import time

from .source import ElevationSource, FlatElevationSource, DemElevationSource, build_elevation_source
from .streaming import TerrainCache, terrain_cache, tile_name


class WorldElevation:
    def __init__(self, source, grid_size, geoid_separation_m=0.0, cache=None, surface=None):
        self.source = source
        self.grid_size = grid_size
        self.geoid_separation_m = geoid_separation_m
        self.cache = cache
        self.surface = surface
        self.available = not isinstance(source, FlatElevationSource) or cache is not None

    def ground_elevation_asl_m(self, latitude_deg, longitude_deg):
        value = self.source.elevation_asl_m(latitude_deg, longitude_deg)
        if self.cache:
            value = self.cache.sample(latitude_deg, longitude_deg, value)
        return value

    def elevation_asl_m(self, latitude_deg, longitude_deg):
        value = self.ground_elevation_asl_m(latitude_deg, longitude_deg)
        return self.surface(latitude_deg, longitude_deg, value) if self.surface else value

    def grid(self, bounds):
        started = time.perf_counter()
        west, south, east, north = bounds
        size = self.grid_size
        bottom = math.asinh(math.tan(math.radians(south)))
        top = math.asinh(math.tan(math.radians(north)))
        latitudes = [math.degrees(math.atan(math.sinh(top + (bottom - top) * row / (size - 1)))) for row in range(size)]
        heights = [round(self.elevation_asl_m(latitude, west + (east - west) * col / (size - 1)) + self.geoid_separation_m, 3)
                   for latitude in latitudes for col in range(size)]
        return {'size': size, 'latitudes': latitudes, 'heights_m': heights,
                'terrain_grid_ms': round((time.perf_counter() - started) * 1000, 2)}

import math

MERCATOR_LATITUDE_LIMIT_DEG = 85.05112878


def tile_xy(longitude, latitude, level):
    size = 2 ** level
    latitude = max(-MERCATOR_LATITUDE_LIMIT_DEG, min(MERCATOR_LATITUDE_LIMIT_DEG, latitude))
    return (int((longitude + 180) / 360 * size),
            int((1 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2 * size))


def tile_bounds(level, x, y):
    size = 2 ** level
    latitude = lambda row: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / size))))
    return [x / size * 360 - 180, latitude(y + 1), (x + 1) / size * 360 - 180, latitude(y)]

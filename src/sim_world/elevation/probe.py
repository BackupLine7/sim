import math
from .streaming import tile_name


def elevation_probe(elevation, latitude, longitude):
    if elevation is None:
        raise ValueError('Источник высот не настроен')
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -85<=latitude<=85 or not -180<=longitude<=180:
        raise ValueError('Некорректные координаты')
    cache=elevation.cache
    if cache is None:
        return dict(ready=True,elevation_asl_m=elevation.source.elevation_asl_m(latitude,longitude))
    key=tile_name(latitude,longitude)
    with cache.lock:
        cache.suppressed.discard(key)
        cache.request(latitude,longitude)
        value=cache.sample(latitude,longitude,math.nan,protect_flight=False)
        if math.isfinite(value):
            return dict(ready=True,elevation_asl_m=value)
        if key in cache.errors:
            raise ValueError('Не удалось загрузить рельеф: '+cache.errors[key])
        if not cache.enabled and key not in cache.pending:
            raise ValueError('Нет высот для этой точки. Включите загрузку рельефа или задайте высоту вручную.')
        if key in cache.tiles:
            raise ValueError('В данных рельефа нет высоты для этой точки. Укажите её вручную.')
    return dict(ready=False)

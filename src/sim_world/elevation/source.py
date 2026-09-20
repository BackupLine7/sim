from __future__ import annotations

import math
from abc import ABC, abstractmethod
from pathlib import Path


class ElevationSource(ABC):

    @abstractmethod
    def elevation_asl_m(self, latitude_deg: float, longitude_deg: float) -> float:
        ...

    @abstractmethod
    def describe(self) -> str:
        ...


class FlatElevationSource(ElevationSource):

    def __init__(self, elevation_asl_m: float) -> None:
        self._elevation_asl_m = elevation_asl_m

    def elevation_asl_m(self, latitude_deg: float, longitude_deg: float) -> float:
        return self._elevation_asl_m

    def describe(self) -> str:
        return f"плоская земля на {self._elevation_asl_m:.1f} м над уровнем моря"


class DemElevationSource(ElevationSource):

    _WGS84_EPSG = 4326

    def __init__(
        self,
        dem_path: Path,
        fallback_elevation_asl_m: float,
        geoid_separation_m: float = 0.0,
        in_memory_limit_mb: int = 256,
    ) -> None:
        import rasterio
        from pyproj import Transformer

        self._dem_path = dem_path
        self._fallback_elevation_asl_m = fallback_elevation_asl_m
        self._geoid_separation_m = geoid_separation_m

        self._dataset = rasterio.open(dem_path)
        self._nodata = self._dataset.nodata



        self._to_dem_crs = Transformer.from_crs(
            f"EPSG:{self._WGS84_EPSG}", self._dataset.crs, always_xy=True
        )

        size_mb = dem_path.stat().st_size / (1024 * 1024)
        self._held_in_memory = size_mb <= in_memory_limit_mb
        self._grid = self._dataset.read(1) if self._held_in_memory else None

    def elevation_asl_m(self, latitude_deg: float, longitude_deg: float) -> float:
        x, y = self._to_dem_crs.transform(longitude_deg, latitude_deg)


        row_f, col_f = self._dataset.index(x, y, op=lambda value: value)
        height_m = self._sample_bilinear(float(row_f) - 0.5, float(col_f) - 0.5)

        if height_m is None:
            return self._fallback_elevation_asl_m
        return height_m + self._geoid_separation_m

    def _sample_bilinear(self, row_f: float, col_f: float) -> float | None:
        row0, col0 = math.floor(row_f), math.floor(col_f)
        row_frac, col_frac = row_f - row0, col_f - col0

        corners = [
            self._raw_value(row0, col0),
            self._raw_value(row0, col0 + 1),
            self._raw_value(row0 + 1, col0),
            self._raw_value(row0 + 1, col0 + 1),
        ]
        if any(value is None for value in corners):
            return None

        top_left, top_right, bottom_left, bottom_right = corners
        top = top_left + (top_right - top_left) * col_frac
        bottom = bottom_left + (bottom_right - bottom_left) * col_frac
        return top + (bottom - top) * row_frac

    def _raw_value(self, row: int, col: int) -> float | None:
        if not (0 <= row < self._dataset.height and 0 <= col < self._dataset.width):
            return None

        if self._held_in_memory:
            value = float(self._grid[row, col])
        else:
            import rasterio.windows

            window = rasterio.windows.Window(col, row, 1, 1)
            value = float(self._dataset.read(1, window=window)[0, 0])

        if self._nodata is not None and value == self._nodata:
            return None
        if math.isnan(value):
            return None
        return value

    def describe(self) -> str:
        pixel_size_m = abs(self._dataset.transform.a)
        placement = "в памяти" if self._held_in_memory else "чтением с диска"
        return (
            f"DEM {self._dem_path.name}: сетка {self._dataset.width}x{self._dataset.height}, "
            f"шаг ~{pixel_size_m:.1f}, поправка на геоид "
            f"{self._geoid_separation_m:+.1f} м, читается {placement}"
        )

    def close(self) -> None:
        self._dataset.close()


def build_elevation_source(terrain_config) -> ElevationSource:
    if not terrain_config.dem_path.exists():
        return FlatElevationSource(terrain_config.fallback_elevation_asl_m)

    return DemElevationSource(
        dem_path=terrain_config.dem_path,
        fallback_elevation_asl_m=terrain_config.fallback_elevation_asl_m,
        geoid_separation_m=terrain_config.geoid_separation_m,
        in_memory_limit_mb=terrain_config.in_memory_limit_mb,
    )
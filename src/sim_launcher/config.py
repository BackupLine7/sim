"""Чтение и проверка настроек симулятора.

Единственное место, которое знает формат файла настроек. Остальные модули
получают готовые типизированные объекты и про YAML ничего не знают — заменить
YAML на что угодно можно правкой одного этого файла.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Настройки прочитаны, но в них что-то не сходится."""


@dataclass(frozen=True)
class PolygonConfig:
    """Учебный полигон и точка старта аппарата."""

    name: str
    home_latitude_deg: float
    home_longitude_deg: float
    home_elevation_asl_m: float
    home_heading_deg: float


@dataclass(frozen=True)
class TerrainConfig:
    """Откуда берутся высоты рельефа и как часто они уходят в физику."""

    dem_path: Path
    geoid_separation_m: float
    update_hz: float
    max_change_rate_m_per_s: float
    fallback_elevation_asl_m: float
    in_memory_limit_mb: int

    @property
    def update_period_s(self) -> float:
        return 1.0 / self.update_hz


@dataclass(frozen=True)
class ArduPilotConfig:
    """Запуск автопилота в режиме программной симуляции (SITL)."""

    sim_vehicle_path: Path
    vehicle: str
    frame: str
    extra_args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JsbSimConfig:
    """Модель планера и сетевые порты обмена с JSBSim."""

    aircraft_model: str
    fdm_port_base: int
    console_port_base: int
    terrain_input_port_base: int
    pose_output_port_base: int
    pose_output_hz: float
    pose_output_host: str
    port_stride: int
    bind_host: str

    def terrain_input_port(self, instance_index: int) -> int:
        """Порт, куда МЫ шлём высоту рельефа для указанного ученика."""
        return self.terrain_input_port_base + instance_index * self.port_stride

    def pose_output_port(self, instance_index: int) -> int:
        """Порт, откуда МЫ читаем позу аппарата для картинки в браузере."""
        return self.pose_output_port_base + instance_index * self.port_stride

    def fdm_port(self, instance_index: int) -> int:
        """Порт, откуда идёт поток состояния аппарата (его занимает ArduPilot)."""
        return self.fdm_port_base + instance_index * self.port_stride


@dataclass(frozen=True)
class StudentsConfig:
    """Сколько рабочих мест поднимать и с какого номера нумеровать."""

    count: int
    first_instance_index: int

    @property
    def instance_indexes(self) -> list[int]:
        start = self.first_instance_index
        return list(range(start, start + self.count))


@dataclass(frozen=True)
class SimulationConfig:
    """Все настройки симулятора целиком."""

    polygon: PolygonConfig
    terrain: TerrainConfig
    ardupilot: ArduPilotConfig
    jsbsim: JsbSimConfig
    students: StudentsConfig
    project_root: Path


def load_simulation_config(config_path: Path) -> SimulationConfig:
    """Прочитать файл настроек и проверить его на осмысленность.

    Пути внутри файла считаются относительно корня проекта — каталога, где
    лежит `config/`. Так один и тот же файл работает независимо от того, из
    какого каталога запущен процесс.
    """
    config_path = config_path.resolve()
    project_root = config_path.parent.parent

    with config_path.open(encoding="utf-8") as stream:
        raw: dict[str, Any] = yaml.safe_load(stream) or {}
    active_start=project_root/'config/local.start-active.json'
    if active_start.exists():
        import json
        start=json.loads(active_start.read_text(encoding='utf-8'))
        raw['polygon'].update(home_latitude_deg=start['latitude_deg'],home_longitude_deg=start['longitude_deg'],home_elevation_asl_m=start['elevation_asl_m'],home_heading_deg=start['heading_deg'])

    def section(name: str) -> dict[str, Any]:
        if name not in raw:
            raise ConfigError(f"В {config_path} нет раздела '{name}'")
        return raw[name]

    def resolve(path_text: str) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else (project_root / path)

    terrain_raw = section("terrain")
    jsbsim_raw = section("jsbsim")
    students_raw = section("students")
    ardupilot_raw = section("ardupilot")

    config = SimulationConfig(
        polygon=PolygonConfig(**section("polygon")),
        terrain=TerrainConfig(
            dem_path=resolve(terrain_raw["dem_path"]),
            geoid_separation_m=float(terrain_raw["geoid_separation_m"]),
            update_hz=float(terrain_raw["update_hz"]),
            max_change_rate_m_per_s=float(terrain_raw["max_change_rate_m_per_s"]),
            fallback_elevation_asl_m=float(terrain_raw["fallback_elevation_asl_m"]),
            in_memory_limit_mb=int(terrain_raw["in_memory_limit_mb"]),
        ),
        ardupilot=ArduPilotConfig(
            sim_vehicle_path=resolve(ardupilot_raw["sim_vehicle_path"]),
            vehicle=ardupilot_raw["vehicle"],
            frame=ardupilot_raw["frame"],
            extra_args=list(ardupilot_raw.get("extra_args", [])),
        ),
        jsbsim=JsbSimConfig(**jsbsim_raw),
        students=StudentsConfig(**students_raw),
        project_root=project_root,
    )

    _validate(config, config_path)
    return config


def _validate(config: SimulationConfig, config_path: Path) -> None:
    """Отсечь настройки, которые сломаются не сразу, а через час занятия."""
    if config.terrain.update_hz <= 0:
        raise ConfigError("terrain.update_hz должен быть больше нуля")

    if config.terrain.max_change_rate_m_per_s <= 0:
        raise ConfigError(
            "terrain.max_change_rate_m_per_s должен быть больше нуля: "
            "без предела первая же посылка высоты аэродрома разрушит физику"
        )

    if config.students.count < 1:
        raise ConfigError("students.count должен быть хотя бы 1")

    # Порты соседних учеников не должны накладываться: свои порты JSBSim
    # занимает подряд от базового, и слишком мелкий шаг тихо сведёт двух
    # учеников в один экземпляр физики.
    minimal_stride = 2
    if config.jsbsim.port_stride < minimal_stride:
        raise ConfigError(
            f"jsbsim.port_stride={config.jsbsim.port_stride} слишком мал: "
            f"порты учеников наложатся друг на друга, нужно минимум {minimal_stride}"
        )

    if not config.ardupilot.sim_vehicle_path.exists():
        raise ConfigError(
            f"Не найден sim_vehicle.py по пути {config.ardupilot.sim_vehicle_path}. "
            f"Субмодули подтянуты? Проверьте: git submodule update --init"
        )

    if not config.terrain.dem_path.exists():
        # Не ошибка: без DEM симулятор запускается на плоской земле. Но
        # предупредить надо громко — иначе решат, что рельеф работает.
        print(
            f"[конфиг] ВНИМАНИЕ: файл рельефа {config.terrain.dem_path} не найден.\n"
            f"[конфиг] Земля будет ПЛОСКОЙ на высоте "
            f"{config.terrain.fallback_elevation_asl_m} м. "
            f"Проверено по {config_path}."
        )

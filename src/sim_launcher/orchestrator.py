"""Поднимает и гасит рабочие места учеников.

Всё, что знает про «их пятеро». Отдельные экземпляры про это не знают и
запускаются поодиночке.
"""

from __future__ import annotations

from .config import SimulationConfig
from .sitl_instance import SitlInstance
from sim_world.elevation.source import ElevationSource, build_elevation_source


class SimulationOrchestrator:
    """Занятие целиком: N рабочих мест на общем источнике высот."""

    def __init__(self, config: SimulationConfig) -> None:
        self._config = config
        # Источник высот один на всех: файл DEM читается в память один раз, а
        # не по копии на ученика. При пяти учениках это разница в пять
        # гигабайт на съёмке высокого разрешения.
        self._elevation_source: ElevationSource = build_elevation_source(config.terrain)
        self._instances: list[SitlInstance] = []

    @property
    def elevation_source(self) -> ElevationSource:
        return self._elevation_source

    def start_all(self) -> None:
        print(f"[занятие] полигон: {self._config.polygon.name}")
        print(f"[занятие] высоты: {self._elevation_source.describe()}")

        for instance_index in self._config.students.instance_indexes:
            instance = SitlInstance(instance_index, self._config, self._elevation_source)
            instance.start()
            self._instances.append(instance)

        print(f"[занятие] поднято рабочих мест: {len(self._instances)}")

    def stop_all(self) -> None:
        # Гасим в обратном порядке: последний поднятый мешает меньше всех.
        for instance in reversed(self._instances):
            instance.stop()
        self._instances.clear()
        print("[занятие] все рабочие места остановлены")

    def running_count(self) -> int:
        return sum(1 for instance in self._instances if instance.is_running)

    def __enter__(self) -> "SimulationOrchestrator":
        self.start_all()
        return self

    def __exit__(self, *_exception_details) -> None:
        self.stop_all()

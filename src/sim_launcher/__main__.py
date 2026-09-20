"""Запуск симулятора.

    python -m sim_launcher                          # поднять занятие
    python -m sim_launcher --check                  # проверить настройки и выйти
    python -m sim_launcher --config путь/к/файлу.yaml
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

from .config import ConfigError, load_simulation_config
from .orchestrator import SimulationOrchestrator

DEFAULT_CONFIG_RELATIVE_PATH = Path("config") / "simulation.yaml"


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()

    parser = argparse.ArgumentParser(description="Учебный симулятор БПЛА: запуск занятия")
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="файл настроек занятия",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="только проверить настройки и источник высот, ничего не запуская",
    )
    parser.add_argument(
        "--terrain-only",
        action="store_true",
        help=(
            "только подача рельефа, без запуска SITL: физика уже работает "
            "где-то ещё, например в контейнере"
        ),
    )
    arguments = parser.parse_args(argv)

    try:
        config = load_simulation_config(arguments.config)
    except (ConfigError, OSError, KeyError, TypeError) as error:
        print(f"[ошибка настроек] {error}", file=sys.stderr)
        return 2

    if arguments.check:
        return _check_only(config)

    if arguments.terrain_only:
        return _terrain_only(config)

    stop_requested = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_requested.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_requested.set())

    with SimulationOrchestrator(config):
        print("[занятие] работаю. Ctrl+C — остановить.")
        stop_requested.wait()
        print("\n[занятие] останавливаюсь...")

    return 0


def _terrain_only(config) -> int:
    """Подавать рельеф в уже работающую физику.

    Нужно, когда SITL поднят отдельно — например, в контейнере Linux, а
    разработка идёт на Windows. Разделение честное: подача рельефа ничего не
    знает про то, кто и как запустил физику, ей нужен только адрес сокета.
    """
    from .jsbsim_terrain_feeder import JsbSimTerrainFeeder
    from sim_world.elevation.source import build_elevation_source

    elevation_source = build_elevation_source(config.terrain)
    polygon = config.polygon
    print(f"[рельеф] высоты: {elevation_source.describe()}")

    feeders = []
    for instance_index in config.students.instance_indexes:
        feeder = JsbSimTerrainFeeder(
            host=config.jsbsim.bind_host,
            command_port=config.jsbsim.terrain_input_port(instance_index),
            elevation_source=elevation_source,
            position_provider=lambda: (
                polygon.home_latitude_deg,
                polygon.home_longitude_deg,
            ),
            update_period_s=config.terrain.update_period_s,
            instance_index=instance_index,
            max_change_rate_m_per_s=config.terrain.max_change_rate_m_per_s,
            home_elevation_asl_m=polygon.home_elevation_asl_m,
        )
        feeder.start()
        feeders.append(feeder)

    stop_requested = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_requested.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_requested.set())

    print("[рельеф] подаю. Ctrl+C — остановить.")
    stop_requested.wait()

    for feeder in feeders:
        feeder.stop()
    print("[рельеф] остановлено")
    return 0


def _check_only(config) -> int:
    """Прогнать всё, что можно проверить без запуска процессов."""
    orchestrator = SimulationOrchestrator(config)
    polygon = config.polygon

    print(f"[проверка] полигон: {polygon.name}")
    print(f"[проверка] высоты: {orchestrator.elevation_source.describe()}")

    # Контрольная сверка: что источник высот думает про точку старта. Если это
    # число сильно расходится с home_elevation_asl_m из настроек — почти
    # наверняка не выставлена поправка на геоид, и самолёт будет летать на
    # десятки метров ниже нарисованной земли.
    elevation_at_home_m = orchestrator.elevation_source.elevation_asl_m(
        polygon.home_latitude_deg, polygon.home_longitude_deg
    )
    difference_m = elevation_at_home_m - polygon.home_elevation_asl_m

    print(f"[проверка] высота под точкой старта по данным: {elevation_at_home_m:.1f} м")
    print(f"[проверка] в настройках указано:               {polygon.home_elevation_asl_m:.1f} м")
    print(f"[проверка] расхождение:                        {difference_m:+.1f} м")

    suspicious_difference_m = 5.0
    if abs(difference_m) > suspicious_difference_m:
        print(
            f"[проверка] ВНИМАНИЕ: расхождение больше {suspicious_difference_m:.0f} м. "
            f"Похоже на неучтённую разницу систем отсчёта высоты — проверьте "
            f"terrain.geoid_separation_m."
        )

    print(f"[проверка] рабочих мест будет поднято: {config.students.count}")
    for instance_index in config.students.instance_indexes:
        console_port = (
            config.jsbsim.console_port_base + instance_index * config.jsbsim.port_stride
        )
        print(
            f"[проверка]   #{instance_index}: "
            f"состояние {config.jsbsim.fdm_port(instance_index)}, "
            f"рули {console_port} (занимает ArduPilot), "
            f"рельеф {config.jsbsim.terrain_input_port(instance_index)} (наш)"
        )
    return 0


def _force_utf8_output() -> None:
    """Русский текст в журнале должен читаться и в консоли Windows.

    По умолчанию она работает в кодировке cp866/cp1251, и сообщения приходят
    нечитаемым набором символов — оператор не поймёт, что сломалось.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _default_config_path() -> Path:
    """Настройки рядом с проектом, а не с текущим каталогом запуска."""
    project_root = Path(__file__).resolve().parents[2]
    return project_root / DEFAULT_CONFIG_RELATIVE_PATH


if __name__ == "__main__":
    raise SystemExit(main())

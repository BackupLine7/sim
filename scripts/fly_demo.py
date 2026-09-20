#!/usr/bin/env python3
"""Показательный полёт: взлёт и круг над полигоном.

Нужен, чтобы увидеть работающую цепочку целиком — физика, автопилот, мост,
картинка в браузере. Не часть тренажёра: учебные задания будут задаваться
иначе, через сценарии инструктора.

    python scripts/fly_demo.py [--instance 0]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from pymavlink import mavutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sim_launcher.config import load_simulation_config  # noqa: E402

MAVLINK_PORT_BASE = 5760
PORT_STRIDE = 10

TAKEOFF_ALTITUDE_M = 150.0
CIRCLE_ALTITUDE_M = 200.0
CIRCLE_OFFSET_DEG = 0.012  # примерно полтора километра в сторону


def log(message: str) -> None:
    print(f"[полёт] {message}", flush=True)


def connect(instance_index: int):
    port = MAVLINK_PORT_BASE + instance_index * PORT_STRIDE
    log(f"подключаюсь к автопилоту на tcp:127.0.0.1:{port}")
    link = mavutil.mavlink_connection(f"tcp:127.0.0.1:{port}")
    link.wait_heartbeat(timeout=60)
    log(f"есть связь: система {link.target_system}")
    return link


def set_parameter(link, name: str, value: float) -> None:
    link.mav.param_set_send(
        link.target_system,
        link.target_component,
        name.encode("ascii"),
        value,
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
    )
    time.sleep(0.3)


def upload_mission(link, home_latitude_deg: float, home_longitude_deg: float) -> None:
    """Взлёт, затем бесконечный круг в стороне от полосы.

    Первой точкой идёт заглушка: ArduPilot считает точку номер 0 домом, а не
    командой, и любое задание, положенное туда, молча пропадает. Без неё взлёт
    исчезает, аппарат остаётся на полосе с нулевым газом и без объяснений.
    """
    points = [
        (
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,  # заглушка под дом
            home_latitude_deg,
            home_longitude_deg,
            0.0,
        ),
        (
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            home_latitude_deg,
            home_longitude_deg,
            TAKEOFF_ALTITUDE_M,
        ),
        (
            mavutil.mavlink.MAV_CMD_NAV_LOITER_UNLIM,
            home_latitude_deg + CIRCLE_OFFSET_DEG,
            home_longitude_deg + CIRCLE_OFFSET_DEG,
            CIRCLE_ALTITUDE_M,
        ),
    ]

    link.mav.mission_count_send(link.target_system, link.target_component, len(points))
    for _ in points:
        request = link.recv_match(
            type=["MISSION_REQUEST", "MISSION_REQUEST_INT"], blocking=True, timeout=10
        )
        if request is None:
            raise TimeoutError("автопилот не запросил точку задания")

        command, latitude_deg, longitude_deg, altitude_m = points[request.seq]
        link.mav.mission_item_int_send(
            link.target_system,
            link.target_component,
            request.seq,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            command,
            0,
            1,
            0, 0, 0, 0,
            int(latitude_deg * 1e7),
            int(longitude_deg * 1e7),
            altitude_m,
        )

    acknowledgement = link.recv_match(type="MISSION_ACK", blocking=True, timeout=10)
    log(f"полётное задание принято: {acknowledgement.type if acknowledgement else 'нет ответа'}")


def watch_flight(link, seconds: float) -> None:
    """Показывать высоту и скорость, пока идёт взлёт."""
    started_at = time.monotonic()
    while time.monotonic() - started_at < seconds:
        message = link.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=5)
        if message is None:
            continue
        altitude_agl_m = message.relative_alt / 1000.0
        ground_speed_ms = (message.vx**2 + message.vy**2) ** 0.5 / 100.0
        log(
            f"t={time.monotonic() - started_at:5.1f} с   "
            f"над землёй {altitude_agl_m:7.1f} м   "
            f"скорость {ground_speed_ms:5.1f} м/с"
        )
        time.sleep(1.0)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=int, default=0)
    parser.add_argument("--watch-seconds", type=float, default=60.0)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "simulation.yaml")
    arguments = parser.parse_args()

    config = load_simulation_config(arguments.config)
    polygon = config.polygon

    link = connect(arguments.instance)

    # Проверки перед взлётом выключаем: это показательный полёт на месте, где
    # нет ни настоящего приёмника спутников, ни компаса. В учебных сценариях
    # они, наоборот, нужны — на них построена отработка отказов.
    log("отключаю предполётные проверки (только для показа)")
    set_parameter(link, "ARMING_CHECK", 0)

    # ArduPlane по умолчанию ждёт толчка рукой или разбега, прежде чем дать
    # газ. Здесь ни того, ни другого нет: нули означают "начинать сразу".
    for name, value in (
        ("TKOFF_THR_MINACC", 0),
        ("TKOFF_THR_MINSPD", 0),
        ("TKOFF_THR_MAX", 100),
        ("THR_FAILSAFE", 0),  # пульта нет, иначе автопилот считает это отказом
    ):
        set_parameter(link, name, value)

    upload_mission(link, polygon.home_latitude_deg, polygon.home_longitude_deg)

    log("режим AUTO")
    link.set_mode_apm("AUTO")
    time.sleep(1.0)

    log("запускаю двигатель")
    link.mav.command_long_send(
        link.target_system, link.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0,
    )
    time.sleep(2.0)

    log("взлёт")
    watch_flight(link, arguments.watch_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

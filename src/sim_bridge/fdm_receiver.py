"""Приём позы аппарата напрямую от физики.

JSBSim шлёт сюда положение и углы 50 раз в секунду через свой выходной сокет,
объявленный в scripts/prepare_jsbsim_root.py.

Почему не из MAVLink. MAVLink отдаёт положение 4-10 раз в секунду — модель на
глобусе на такой частоте дёргается. MAVLink пойдёт на приборы и статусы, где
5 Гц более чем достаточно.
"""

from __future__ import annotations

import asyncio
import math
from typing import Callable

FEET_PER_METER = 3.280839895

#: Порядок полей задан в scripts/prepare_jsbsim_root.py, POSE_PROPERTIES.
#: Первым JSBSim всегда шлёт время симуляции, его в том списке нет.
POSE_FIELD_NAMES = [
    "sim_time_s",
    "latitude_deg",
    "longitude_deg",
    "altitude_asl_m",
    "roll_deg",
    "pitch_deg",
    "yaw_deg",
    "airspeed_kt",
    "altitude_agl_ft",
]

PoseHandler = Callable[[dict], None]


class FdmPoseProtocol(asyncio.DatagramProtocol):
    """Разбирает пакеты JSBSim и отдаёт готовую позу дальше."""

    def __init__(
        self, on_pose: PoseHandler, instance_index: int, home_elevation_asl_m: float
    ) -> None:
        self._on_pose = on_pose
        self._instance_index = instance_index
        self._home_elevation_asl_m = home_elevation_asl_m
        self._received_count = 0

    def datagram_received(self, data: bytes, _address) -> None:
        pose = self._parse(data)
        if pose is None:
            return
        self._received_count += 1
        self._on_pose(pose)

    def _parse(self, data: bytes) -> dict | None:
        """Строка чисел через разделитель. Заголовок и мусор молча пропускаем.

        Пропускаем, а не падаем: JSBSim шлёт первой строкой названия полей, и
        занятие не должно прерываться из-за одного нечитаемого пакета.
        """
        text = data.decode("ascii", errors="ignore").strip()
        parts = text.replace(",", "\t").split()
        if len(parts) < len(POSE_FIELD_NAMES):
            return None

        try:
            values = [float(part) for part in parts[: len(POSE_FIELD_NAMES)]]
        except ValueError:
            return None  # заголовок с названиями полей

        if any(not math.isfinite(value) for value in values):
            # Физика развалилась. Лучше замереть на последней здоровой позе,
            # чем дёрнуть модель в никуда на глазах у ученика.
            return None

        pose = dict(zip(POSE_FIELD_NAMES, values))

        # JSBSim отсчитывает высоту не от уровня моря, а от точки старта:
        # в круге на 330 метрах он присылает 151. Cesium ждёт настоящую
        # высоту над уровнем моря, иначе нарисует аппарат на высоту аэродрома
        # ниже, чем он летит — и на холмистом полигоне внутри склона.
        pose["altitude_asl_m"] += self._home_elevation_asl_m() if callable(self._home_elevation_asl_m) else self._home_elevation_asl_m
        pose["altitude_agl_m"] = pose["altitude_agl_ft"] / FEET_PER_METER
        pose["instance_index"] = self._instance_index
        return pose

    @property
    def received_count(self) -> int:
        return self._received_count


async def listen_for_pose(
    host: str,
    port: int,
    instance_index: int,
    on_pose: PoseHandler,
    home_elevation_asl_m: float,
):
    """Открыть приём позы для одного ученика."""
    loop = asyncio.get_running_loop()
    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: FdmPoseProtocol(on_pose, instance_index, home_elevation_asl_m),
        local_addr=(host, port),
    )
    return transport

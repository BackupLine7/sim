"""Подача высоты рельефа в JSBSim.

Зачем это нужно. ArduPilot в режиме JSBSim высоту над землёй не считает сам, а
берёт готовую от JSBSim (см. SIM_JSBSim.cpp, `fdm.agl*100 + home.alt`). JSBSim
же без подсказки использует поверхность постоянной высоты на эллипсоиде. При перепаде высот на полигоне в сотни
метров это значит, что самолёт пролетает сквозь холмы, которых физика не видит.

Правим это СНАРУЖИ, по правилу 2 из CLAUDE.md: чужой файл в third_party не
трогаем, а сами пишем JSBSim переменную `position/terrain-elevation-asl-ft`
через его командный сокет.

Частота 5-10 Гц достаточна: самолёт идёт ~30 м/с, за такт при 10 Гц проходит
3 метра — десятую часть ячейки 30-метровой сетки.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Callable

from sim_world.elevation.source import ElevationSource

METERS_PER_FOOT = 0.3048

#: Переменная JSBSim, куда пишется высота рельефа. Объявлена в его исходниках,
#: FGPropagate.cpp. Единицы — футы, отсюда пересчёт из метров.
TERRAIN_ELEVATION_PROPERTY = "position/terrain-elevation-asl-ft"

#: Откуда брать текущее положение аппарата. Пока поток состояния не подключён,
#: сюда подставляется точка старта — рельеф под стоящим на земле аппаратом
#: считается верно, и это уже проверяемо.
PositionProvider = Callable[[], tuple[float, float]]


class JsbSimTerrainFeeder:
    """Сообщает одному экземпляру JSBSim, какая под ним земля.

    Один объект — один ученик. Работает в своём потоке, останавливается по
    `stop()`. Сбои связи не роняют занятие: соединение переустанавливается, а
    физика тем временем продолжает считать с последним известным значением.
    """

    def __init__(
        self,
        host: str,
        command_port: int,
        elevation_source: ElevationSource,
        position_provider: PositionProvider,
        update_period_s: float,
        instance_index: int,
        max_change_rate_m_per_s: float,
        home_elevation_asl_m: float,
        reconnect_delay_s: float = 2.0,
    ) -> None:
        self._host = host
        self._command_port = command_port
        self._elevation_source = elevation_source
        self._position_provider = position_provider
        self._update_period_s = update_period_s
        self._instance_index = instance_index
        self._max_change_rate_m_per_s = max_change_rate_m_per_s
        self._home_elevation_asl_m = home_elevation_asl_m
        self._reconnect_delay_s = reconnect_delay_s

        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection: socket.socket | None = None
        self._last_sent_elevation_asl_m: float | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Подача рельефа уже запущена")
        self._thread = threading.Thread(
            target=self._run, name=f"terrain-feeder-{self._instance_index}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout_s: float = 5.0) -> None:
        self._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None
        self._close_connection()

    @property
    def last_sent_elevation_asl_m(self) -> float | None:
        """Что ушло в физику последним. Нужно оператору для разбора расхождений."""
        return self._last_sent_elevation_asl_m

    def _run(self) -> None:
        while not self._stop_requested.is_set():
            cycle_started_at = time.monotonic()
            try:
                self._send_current_elevation()
            except OSError as error:
                self._log(f"связь с JSBSim потеряна ({error}), переподключаюсь")
                self._close_connection()
                self._stop_requested.wait(self._reconnect_delay_s)
                continue

            # Ждём остаток такта, а не фиксированную паузу: иначе медленное
            # чтение DEM тихо снижает реальную частоту подачи.
            elapsed_s = time.monotonic() - cycle_started_at
            self._stop_requested.wait(max(0.0, self._update_period_s - elapsed_s))

    def _send_current_elevation(self) -> None:
        latitude_deg, longitude_deg = self._position_provider()
        target_elevation_asl_m = self._elevation_source.elevation_asl_m(
            latitude_deg, longitude_deg
        )
        # JSBSim ведёт высоты не от уровня моря, а от точки старта: проверено
        # на живом запуске — стоящий на аэродроме высотой 179 м аппарат
        # показывает высоту 0.4 м. Высоту аэродрома ArduPilot прибавляет сам
        # (SIM_JSBSim.cpp: fdm.agl*100 + home.alt).
        #
        # Поэтому подаём ПРЕВЫШЕНИЕ над аэродромом, а не абсолютную высоту.
        above_home_m = self._rate_limited(
            target_elevation_asl_m - self._home_elevation_asl_m
        )
        above_home_ft = above_home_m / METERS_PER_FOOT

        command = f"set {TERRAIN_ELEVATION_PROPERTY} {above_home_ft:.3f}\n"
        self._ensure_connected().sendall(command.encode("ascii"))
        self._last_sent_elevation_asl_m = above_home_m

    def _rate_limited(self, target_elevation_asl_m: float) -> float:
        """Не дать земле прыгнуть — она разрушает физику под стоящим аппаратом.

        Проверено на JSBSim 1.3.1: в воздухе скачок земли безвреден, а на
        земле подъём на 300 метров за один такт вгоняет стойки шасси в грунт,
        силы уходят в бесконечность, и всё состояние становится NaN.

        После перехода на превышение над аэродромом скачок на старте исчез:
        под самим аэродромом превышение нулевое, а ноль у JSBSim уже стоит.
        Ограничение осталось страховкой для другого случая — аппарат стоит у
        подножия обрыва, и DEM под ним меняется резко. Земля, поднимающаяся
        под стоящим самолётом со скоростью 50 м/с, подбрасывает его в воздух:
        это тоже проверено на живом запуске.

        Предел с большим запасом перекрывает реальность полёта: самолёт на
        30 м/с над склоном в 45 градусов даёт изменение земли ровно 30 м/с.
        """
        previous_m = self._last_sent_elevation_asl_m
        if previous_m is None:
            # Первое значение отдаём от нуля — там, где JSBSim и стоит, пока
            # ему не сказали иного. Иначе первый же шаг был бы скачком.
            previous_m = 0.0

        max_step_m = self._max_change_rate_m_per_s * self._update_period_s
        difference_m = target_elevation_asl_m - previous_m

        if abs(difference_m) <= max_step_m:
            return target_elevation_asl_m

        step_m = max_step_m if difference_m > 0 else -max_step_m
        return previous_m + step_m

    def _ensure_connected(self) -> socket.socket:
        if self._connection is None:
            self._connection = socket.create_connection(
                (self._host, self._command_port), timeout=self._reconnect_delay_s
            )
            self._log(f"подключён к JSBSim на {self._host}:{self._command_port}")
        return self._connection

    def _close_connection(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except OSError:
                pass
            self._connection = None

    def _log(self, message: str) -> None:
        print(f"[рельеф #{self._instance_index}] {message}", flush=True)

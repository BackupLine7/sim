"""Один экземпляр симуляции — одно рабочее место ученика.

Внутри пара процессов: ArduPilot SITL (автопилот) и JSBSim (физика), который
ArduPilot запускает себе сам дочерним процессом. Плюс наша подача высоты
рельефа.

Модуль намеренно ничего не знает про других учеников и про интерфейс. Поднять
его в одиночку из тестов — нормальный сценарий.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import SimulationConfig
from .jsbsim_terrain_feeder import JsbSimTerrainFeeder
from sim_world.elevation.source import ElevationSource


class SitlInstance:
    """Автопилот с физикой для одного ученика."""

    def __init__(
        self,
        instance_index: int,
        config: SimulationConfig,
        elevation_source: ElevationSource,
    ) -> None:
        self._instance_index = instance_index
        self._config = config
        self._elevation_source = elevation_source

        self._process: subprocess.Popen | None = None
        self._terrain_feeder: JsbSimTerrainFeeder | None = None
        self._log_file = None
        self._log_path: Path | None = None

    @property
    def instance_index(self) -> int:
        return self._instance_index

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Поднять автопилот с физикой и начать подавать рельеф."""
        if self.is_running:
            raise RuntimeError(f"Экземпляр {self._instance_index} уже запущен")

        command = self._build_command()
        self._log("запускаю: " + " ".join(command))

        # Вывод SITL уходит в файл, а не в канал процесса. Через канал он
        # упёрся бы в буфер операционной системы (~64 КБ) и встал бы намертво:
        # SITL пишет много, а читать этот канал в нашем коде некому. Заодно
        # инструктору есть куда посмотреть после сбоя.
        self._log_path = self._prepare_log_path()
        self._log_file = self._log_path.open("w", encoding="utf-8", errors="replace")

        self._process = subprocess.Popen(
            command,
            cwd=str(self._config.project_root),
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._log(f"вывод пишется в {self._log_path}")

        self._terrain_feeder = JsbSimTerrainFeeder(
            host=self._config.jsbsim.bind_host,
            # Наш собственный вход, объявленный в описании планера скриптом
            # scripts/prepare_jsbsim_root.py. Командный сокет ArduPilot
            # занимать нельзя: у JSBSim на порт приходится один клиент, второй
            # молча ждёт в очереди.
            command_port=self._config.jsbsim.terrain_input_port(self._instance_index),
            elevation_source=self._elevation_source,
            position_provider=self._current_position,
            update_period_s=self._config.terrain.update_period_s,
            instance_index=self._instance_index,
            max_change_rate_m_per_s=self._config.terrain.max_change_rate_m_per_s,
            home_elevation_asl_m=self._config.polygon.home_elevation_asl_m,
        )
        self._terrain_feeder.start()

    def stop(self, timeout_s: float = 10.0) -> None:
        """Остановить всё, что подняли, в обратном порядке."""
        if self._terrain_feeder is not None:
            self._terrain_feeder.stop()
            self._terrain_feeder = None

        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                self._log("не завершился по-хорошему, снимаю принудительно")
                self._process.kill()
                self._process.wait()
        self._process = None

        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None

    def _build_command(self) -> list[str]:
        """Собрать команду запуска SITL из настроек.

        Ни одного порта и пути прямо здесь — всё приходит из конфига.
        """
        polygon = self._config.polygon
        home = (
            f"{polygon.home_latitude_deg},"
            f"{polygon.home_longitude_deg},"
            f"{polygon.home_elevation_asl_m},"
            f"{polygon.home_heading_deg}"
        )

        # Штатный ключ ArduPilot: где искать описание планера и куда класть
        # свои временные файлы. Указываем на наш подготовленный каталог — в нём
        # у планера объявлен второй входной сокет под рельеф. Так чужой файл в
        # third_party остаётся нетронутым (правило 2).
        jsbsim_root = self._jsbsim_root_path()
        if not jsbsim_root.exists():
            raise FileNotFoundError(
                f"Нет рабочего каталога JSBSim {jsbsim_root}. "
                f"Выполните: python scripts/prepare_jsbsim_root.py"
            )

        command = [
            sys.executable,
            str(self._config.ardupilot.sim_vehicle_path),
            "--vehicle", self._config.ardupilot.vehicle,
            "--frame", self._config.ardupilot.frame,
            "--instance", str(self._instance_index),
            "--custom-location", home,
            "--sim-address", self._config.jsbsim.bind_host,
            "--no-rebuild",
            "--no-mavproxy",
            "--", "--autotest-dir", str(jsbsim_root),
        ]
        command.extend(self._config.ardupilot.extra_args)
        return command

    def _jsbsim_root_path(self) -> Path:
        """Каталог JSBSim этого ученика, собранный scripts/prepare_jsbsim_root.py.

        Путь считается тут, а не берётся из конфига: человеку выбирать нечего,
        а расхождение с генератором дало бы запуск не того планера.
        """
        return (
            self._config.project_root
            / "build"
            / "jsbsim_root"
            / f"instance-{self._instance_index}"
        )

    def _prepare_log_path(self) -> Path:
        """Свой файл журнала на каждого ученика — иначе пять процессов пишут в один."""
        logs_directory = self._config.project_root / "logs"
        logs_directory.mkdir(parents=True, exist_ok=True)
        return logs_directory / f"sitl-{self._instance_index}.log"

    def _current_position(self) -> tuple[float, float]:
        """Где сейчас аппарат: широта и долгота.

        Заглушка на точке старта. Пока поток состояния от JSBSim не подключён,
        рельеф считается под местом взлёта — этого хватает, чтобы проверить,
        что JSBSim вообще принимает нашу высоту. Заменяется на чтение потока
        FDM без правок в остальных модулях: подпись функции остаётся та же.
        """
        polygon = self._config.polygon
        return polygon.home_latitude_deg, polygon.home_longitude_deg

    def _log(self, message: str) -> None:
        print(f"[SITL #{self._instance_index}] {message}", flush=True)

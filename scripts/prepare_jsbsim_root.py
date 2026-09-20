#!/usr/bin/env python3
"""Готовит рабочий каталог JSBSim для каждого ученика.

Зачем это нужно
---------------
ArduPilot запускает JSBSim со своим сгенерированным скриптом и открывает один
командный сокет — для управления рулями. Занять этот же сокет мы не можем: у
JSBSim на порт приходится один клиент, и второе подключение просто ждёт в
очереди, пока первый не отвалится (проверено).

Нам нужен СВОЙ вход, чтобы писать туда высоту рельефа. JSBSim позволяет
объявить сколько угодно входных сокетов, но объявляются они в описании
планера — а оно лежит в third_party, где правки запрещены (правило 2).

Поэтому: генерируем собственную копию описания планера у себя, дописываем в неё
второй входной сокет, и указываем ArduPilot на наш каталог через его штатный
ключ `--autotest-dir`. Чужой файл не тронут, обновление ArduPilot ничего не
ломает — достаточно прогнать этот скрипт заново.

Каталог у каждого ученика свой: порт входа обязан отличаться, иначе пятеро
сойдутся в один экземпляр физики.

Запуск
------
    python scripts/prepare_jsbsim_root.py
    python scripts/prepare_jsbsim_root.py --force   # пересобрать поверх
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sim_launcher.config import SimulationConfig, load_simulation_config  # noqa: E402

#: Куда складываем сгенерированные каталоги. В репозиторий не попадают —
#: это производное от third_party, восстанавливается запуском скрипта.
GENERATED_ROOT_RELATIVE = Path("build") / "jsbsim_root"

#: Откуда берём исходное описание планера. Только чтение.
ARDUPILOT_AIRCRAFT_RELATIVE = Path("third_party/ardupilot/Tools/autotest/aircraft")

FDM_CONFIG_CLOSING_TAG = "</fdm_config>"


def instance_root_path(project_root: Path, instance_index: int) -> Path:
    """Рабочий каталог JSBSim для указанного ученика."""
    return project_root / GENERATED_ROOT_RELATIVE / f"instance-{instance_index}"


def prepare_all(config: SimulationConfig, force: bool = False) -> list[Path]:
    source_aircraft = config.project_root / ARDUPILOT_AIRCRAFT_RELATIVE
    if not source_aircraft.exists():
        raise FileNotFoundError(
            f"Не найдено описание планера: {source_aircraft}. "
            f"Субмодули подтянуты? git submodule update --init"
        )

    prepared: list[Path] = []
    for instance_index in config.students.instance_indexes:
        prepared.append(
            _prepare_one(config, source_aircraft, instance_index, force=force)
        )
    return prepared


def _prepare_one(
    config: SimulationConfig,
    source_aircraft: Path,
    instance_index: int,
    force: bool,
) -> Path:
    target_root = instance_root_path(config.project_root, instance_index)
    target_aircraft = target_root / "aircraft"

    if target_aircraft.exists():
        if not force:
            print(f"[#{instance_index}] уже готов: {target_root}")
            return target_root
        shutil.rmtree(target_aircraft)

    target_aircraft.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_aircraft, target_aircraft)

    terrain_port = config.jsbsim.terrain_input_port(instance_index)
    pose_port = config.jsbsim.pose_output_port(instance_index)
    model_file = _find_model_file(target_aircraft, config.jsbsim.aircraft_model)
    _inject_terrain_input_socket(model_file, terrain_port)
    _inject_pose_output_socket(
        target_root,
        model_file,
        pose_port,
        config.jsbsim.pose_output_hz,
        config.jsbsim.pose_output_host,
    )

    print(
        f"[#{instance_index}] готов: {target_root}, "
        f"вход рельефа {terrain_port}, выход позы {pose_port}"
    )
    return target_root


#: Сокет, объявленный самим планером: <input port="5505"/>. Именно
#: самозакрывающийся тег с портом — теги <input>fcs/что-то</input> внутри
#: цепочек управления называются так же, но это имена величин, не сокеты.
HARDCODED_INPUT_SOCKET = re.compile(r"[ \t]*<input\s+port\s*=\s*\"\d+\"\s*/>\s*\n?")


def _remove_hardcoded_input_sockets(text: str) -> str:
    """Убрать из копии планера жёстко прописанный командный сокет.

    В описании планера от ArduPilot стоит <input port="5505"/>, и тот же порт
    объявляет скрипт запуска, который ArduPilot генерирует сам. JSBSim пытается
    привязать порт дважды, вторая попытка падает с "Could not bind, error = 98",
    и команды на рули до физики не доходят — самолёт стоит на полосе с
    работающим двигателем и нулевой тягой.

    Заодно чинится работа на несколько учеников: 5505 в файле планера один и
    тот же для всех, а ArduPilot ждёт 5505 + номер * 10.

    Правим в СВОЕЙ копии, чужой файл в third_party остаётся нетронутым.
    """
    return HARDCODED_INPUT_SOCKET.sub("", text)


def _find_model_file(aircraft_directory: Path, model_name: str) -> Path:
    model_file = aircraft_directory / model_name / f"{model_name}.xml"
    if not model_file.exists():
        available = sorted(p.name for p in aircraft_directory.iterdir() if p.is_dir())
        raise FileNotFoundError(
            f"Нет описания планера '{model_name}' в {aircraft_directory}. "
            f"Есть: {', '.join(available)}"
        )
    return model_file


def _inject_terrain_input_socket(model_file: Path, terrain_port: int) -> None:
    """Дописать в описание планера второй входной сокет — наш, под рельеф.

    Вставляем перед закрывающим тегом, а не в произвольное место: элементы
    внутри channel тоже называются <input>, и попасть между ними нельзя.
    """
    text = model_file.read_text(encoding="utf-8")

    if FDM_CONFIG_CLOSING_TAG not in text:
        raise ValueError(f"В {model_file} нет тега {FDM_CONFIG_CLOSING_TAG}")

    text = _remove_hardcoded_input_sockets(text)

    socket_declaration = (
        f"\n  <!-- Вход для подачи высоты рельефа. Добавлен скриптом\n"
        f"       scripts/prepare_jsbsim_root.py, вручную не править. -->\n"
        f"  <input port=\"{terrain_port}\"/>\n\n"
    )
    text = text.replace(
        FDM_CONFIG_CLOSING_TAG, socket_declaration + FDM_CONFIG_CLOSING_TAG, 1
    )
    model_file.write_text(text, encoding="utf-8")


#: Что JSBSim шлёт в браузер. Порядок важен: приёмная сторона разбирает по
#: нему. Единицы — те, в которых их отдаёт JSBSim, пересчёт делает мост.
POSE_PROPERTIES = [
    # Именно lat-geod-deg, географическая широта. Похожая на неё lat-gc-deg —
    # геоцентрическая: угол от центра Земли, а не от касательной к её
    # поверхности. На широте Киева они расходятся на 0.19 градуса, то есть на
    # 21 километр, и аппарат оказался бы совсем в другом месте карты.
    ("position/lat-geod-deg", "latitude_deg"),
    ("position/long-gc-deg", "longitude_deg"),
    ("position/h-sl-meters", "altitude_asl_m"),
    ("attitude/phi-deg", "roll_deg"),
    ("attitude/theta-deg", "pitch_deg"),
    ("attitude/psi-deg", "yaw_deg"),
    ("velocities/vtrue-kts", "airspeed_kt"),
    ("position/h-agl-ft", "altitude_agl_ft"),
]


def _inject_pose_output_socket(
    target_root: Path,
    model_file: Path,
    pose_port: int,
    pose_output_hz: float,
    pose_output_host: str,
) -> None:
    """Завести отдельный выход JSBSim с позой аппарата для картинки.

    Зачем отдельный. Собственный выход JSBSim уже занят: через него ArduPilot
    забирает состояние для автопилота. Брать позу для браузера из MAVLink
    нельзя — он отдаёт положение 4-10 раз в секунду, и модель на глобусе
    дёргается. Здесь мы получаем её прямо от физики 50 раз в секунду.

    Описание встроено в файл планера, а не вынесено отдельным файлом: путь к
    внешнему файлу JSBSim ищет относительно каталога планера, и разложить их
    по-разному значит ловить "Could not open file" при каждом переносе.
    """
    newline = chr(10)
    properties = newline.join(
        f"    <property>{jsbsim_name}</property>" for jsbsim_name, _ in POSE_PROPERTIES
    )
    declaration = f'''
  <!-- Поза аппарата для картинки в браузере. Добавлено
       scripts/prepare_jsbsim_root.py, вручную не править. -->
  <output name="{pose_output_host}" type="SOCKET" protocol="UDP" port="{pose_port}" rate="{pose_output_hz:g}">
{properties}
  </output>

'''

    text = model_file.read_text(encoding="utf-8")
    text = text.replace(FDM_CONFIG_CLOSING_TAG, declaration + FDM_CONFIG_CLOSING_TAG, 1)
    model_file.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "config" / "simulation.yaml"
    )
    parser.add_argument(
        "--force", action="store_true", help="пересобрать, даже если каталог уже есть"
    )
    arguments = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    config = load_simulation_config(arguments.config)
    prepared = prepare_all(config, force=arguments.force)
    print(f"Готово: {len(prepared)} рабочих каталогов JSBSim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

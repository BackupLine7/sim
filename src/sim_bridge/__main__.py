"""Мост между физикой и браузером.

Слушает позу от JSBSim по UDP и раздаёт её браузерам по WebSocket. Заодно
отдаёт статические файлы: страницу и саму библиотеку Cesium.

    python -m sim_bridge
    python -m sim_bridge --replay      # без физики, по кругу гоняет тестовый полёт

Ключ --replay нужен, чтобы проверять картинку без запуска SITL: интерфейс
должен работать отдельно от физики, как требует правило 1 из CLAUDE.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

import websockets
from websockets.asyncio.server import serve

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sim_bridge.fdm_receiver import listen_for_pose  # noqa: E402
from sim_bridge.static_server import serve_static_files  # noqa: E402
from sim_launcher.config import load_simulation_config  # noqa: E402
from sim_bridge.flight_control import FlightControl


class PoseHub:
    """Держит подключённые браузеры и рассылает им позу.

    Последняя поза хранится, чтобы только что открытая вкладка сразу увидела
    аппарат, а не ждала следующего пакета.
    """

    def __init__(self, control=None) -> None:
        self.control = control
        self.operator = None
        self._last_pose_at = 0.0
        self._clients = set()
        self._latest_pose_by_instance: dict[int, dict] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def register(self, websocket) -> None:
        self._clients.add(websocket)
        print(f"[мост] браузер подключился, всего: {len(self._clients)}")
        try:
            for pose in self._latest_pose_by_instance.values():
                await websocket.send(json.dumps(pose))
            async for raw in websocket:
                try:
                    message = json.loads(raw)
                    if self.control is None:
                        raise ValueError('Режим просмотра: управление недоступно')
                    if isinstance(message, dict) and message.get('action') == 'release' and self.operator is not websocket:
                        continue
                    action = message.get('action') if isinstance(message, dict) else None
                    if self.operator not in (None, websocket) and action in ('stick', 'release'):
                        continue
                    previous_operator = self.operator
                    # Route preparation samples terrain for seconds; the pose broadcast
                    # shares this loop, so validation runs off it for every command.
                    await asyncio.to_thread(self.control.submit, message)
                    self.operator = None if message.get('action') == 'release' else websocket
                    if previous_operator not in (None, websocket):
                        try:
                            await asyncio.wait_for(previous_operator.send(json.dumps({'type':'control_lost'})),0.1)
                        except (TimeoutError, websockets.exceptions.WebSocketException):
                            pass
                except (ValueError, TypeError) as error:
                    await websocket.send(json.dumps({'type': 'error', 'message': str(error)}))
        finally:
            if self.operator is websocket:
                self.operator = None
                self.control.rc = None
            self._clients.discard(websocket)
            print(f"[мост] браузер отключился, осталось: {len(self._clients)}")

    def publish(self, pose: dict) -> None:
        """Вызывается из приёма UDP. Рассылку отдаём в цикл событий."""
        if self.control and getattr(self.control, 'flight_session', None):
            if self.control.status['phase'] == 'restarting':
                return
            self.control.status['phase'] = self.control.flight_session.update(pose, self.control.status)
            if self.control.status['phase']=='crashed':
                self.control.submit({'type':'command','action':'restart'})
                self._latest_pose_by_instance.clear()
                return
            pose['generation'] = self.control.status['generation']
        if getattr(self, "terrain", None):
            self.terrain.observe(pose)
        self._latest_pose_by_instance[pose["instance_index"]] = pose
        self._last_pose_at = time.monotonic()

    async def broadcast(self):
        # One bounded send per client; slow clients are disconnected, not queued.
        from sim_world.osm_tiles import osm_tile_cache
        cache = osm_tile_cache(self.control.runtime.root) if self.control and self.control.runtime and (self.control.runtime.root/'config/building-streaming.json').exists() else None
        from sim_world.buildings.regions import building_regions
        regions = building_regions(self.control.runtime.root) if cache and (self.control.runtime.root/'config/building-regions.json').exists() else None
        while True:
            packets = list(self._latest_pose_by_instance.values())
            status = dict(self.control.status) if self.control else {'type': 'status', 'mode': 'DEMO', 'connected': False}
            status['physics_live'] = time.monotonic() - self._last_pose_at < 2
            if getattr(self,'terrain',None) and self.terrain.elevation.cache:
                status['terrain_revision']=self.terrain.elevation.cache.revision
            if cache:
                if packets:
                    cache.observe(packets[0])
                status['building_revision'] = f'{cache.revision}:{int(time.monotonic()/cache.settings["retry_s"]) if cache.errors else 0}'
            if regions:
                status['building_revision'] = f"{status.get('building_revision', 0)}:{regions.revision}"
            if (self.control and self.control.runtime and self.control.flight_session.has_flown
                    and not status['physics_live'] and not status.get('restarting')
                    and time.monotonic()-getattr(self,'_last_physics_check',0)>self.control.runtime.settings['stopped_duration_s']):
                self._last_physics_check=time.monotonic()
                try:
                    if await asyncio.to_thread(self.control.runtime.physics_failed) and self.control.flight_session.has_flown:
                        self.control.submit({'type':'command','action':'restart'})
                        self._latest_pose_by_instance.clear()
                except (OSError,TimeoutError):
                    pass
            packets.append(status)
            for client in list(self._clients):
                try:
                    for packet in packets:
                        await asyncio.wait_for(client.send(json.dumps(packet)), timeout=0.1)
                except (TimeoutError, websockets.exceptions.WebSocketException):
                    self._clients.discard(client)
                    await client.close()
            await asyncio.sleep(1 / 30)

    async def _send_safely(self, client, message: str) -> None:
        try:
            await client.send(message)
        except websockets.exceptions.WebSocketException:
            self._clients.discard(client)

    @property
    def client_count(self) -> int:
        return len(self._clients)


async def run_replay(hub: PoseHub, home_latitude_deg: float, home_longitude_deg: float) -> None:
    """Тестовый полёт по кругу — проверка картинки без физики.

    Круг примерно километрового радиуса на высоте 400 метров, оборот за минуту.
    Крен задан постоянным: в развороте самолёт действительно лежит на крыле, и
    вид с борта должен это показывать.
    """
    radius_deg = 0.008
    period_s = 60.0
    started_at = time.monotonic()

    while True:
        elapsed_s = time.monotonic() - started_at
        angle_rad = 2 * math.pi * (elapsed_s % period_s) / period_s

        hub.publish(
            {
                "instance_index": 0,
                "sim_time_s": elapsed_s,
                "latitude_deg": home_latitude_deg + radius_deg * math.cos(angle_rad),
                "longitude_deg": home_longitude_deg + radius_deg * math.sin(angle_rad) * 1.6,
                "altitude_asl_m": 400.0,
                "roll_deg": -25.0,
                "pitch_deg": 2.0,
                "yaw_deg": (math.degrees(angle_rad) + 90.0) % 360.0,
                "airspeed_kt": 45.0,
                "altitude_agl_ft": 720.0,
                "altitude_agl_m": 220.0,
                "replay": True,
            }
        )
        await asyncio.sleep(0.02)  # 50 раз в секунду, как настоящая физика


async def async_main(arguments) -> int:
    config = load_simulation_config(arguments.config)
    from sim_bridge.flight_session import SessionRuntime
    runtime = SessionRuntime(PROJECT_ROOT)
    runtime.prepare()
    control = None if arguments.replay else FlightControl(arguments.mavlink, runtime)
    if control:
        control.start()
    hub = PoseHub(control)
    hub.bind_loop(asyncio.get_running_loop())
    from sim_bridge.terrain_runtime import TerrainRuntime
    terrain = None if arguments.replay else TerrainRuntime(PROJECT_ROOT, config)
    hub.terrain = terrain

    await serve_static_files(PROJECT_ROOT / "web", arguments.host, arguments.http_port, arguments.websocket_port)
    print(f"[мост] страница: http://{arguments.host}:{arguments.http_port}/")

    broadcast_task = asyncio.create_task(hub.broadcast())
    async with serve(hub.register, arguments.host, arguments.websocket_port, max_size=4096):
        print(f"[мост] поза раздаётся на ws://{arguments.host}:{arguments.websocket_port}")

        if arguments.replay:
            print("[мост] режим проверки: тестовый полёт по кругу, физика не нужна")
            await run_replay(
                hub,
                config.polygon.home_latitude_deg,
                config.polygon.home_longitude_deg,
            )
        else:
            for instance_index in config.students.instance_indexes:
                port = config.jsbsim.pose_output_port(instance_index)
                await listen_for_pose(
                    config.jsbsim.bind_host,
                    port,
                    instance_index,
                    hub.publish,
                    lambda: control.runtime.polygon['home_elevation_asl_m'] if control and control.runtime else config.polygon.home_elevation_asl_m,
                )
                print(f"[мост] жду позу ученика #{instance_index} на порту {port}")
            await asyncio.Future()  # работаем, пока не остановят

    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Мост между физикой и браузером")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "simulation.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("--websocket-port", type=int, default=8081)
    parser.add_argument("--mavlink", default="tcp:127.0.0.1:5760")
    parser.add_argument(
        "--replay",
        action="store_true",
        help="тестовый полёт по кругу вместо физики: проверка картинки без SITL",
    )
    arguments = parser.parse_args(argv)

    try:
        return asyncio.run(async_main(arguments))
    except KeyboardInterrupt:
        print("\n[мост] остановлен")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

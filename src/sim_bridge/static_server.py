"""Раздача страницы и библиотеки Cesium.

Отдельный маленький сервер, чтобы для проверки не поднимать nginx. В рабочем
развёртывании статику отдаёт nginx — он же раздаёт тайлы ортофотоплана.
"""

from __future__ import annotations

import asyncio
import mimetypes
import json
from pathlib import Path

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/json", ".json")

HEADER_TERMINATORS = (b"\r\n", b"\n", b"")
WORLD_REQUEST_LIMIT_BYTES = 8192


async def serve_static_files(root: Path, host: str, port: int, websocket_port: int):
    """Поднять раздачу файлов из указанного каталога."""
    handler = _make_handler(root.resolve(), websocket_port)
    return await asyncio.start_server(handler, host, port)


def _make_handler(root: Path, websocket_port: int):
    from sim_bridge.world import simulator_world
    from sim_bridge.world_elevation import SimulatorElevation
    from sim_world import WorldRoutes
    from sim_bridge.preferences import PreferencesStore
    from sim_bridge.missions import MissionStore
    from sim_bridge.start_locations import StartLocations

    world = simulator_world(root.parent)
    preferences = PreferencesStore(root.parent)
    starts = StartLocations(root.parent)
    active_start_version = None

    def reload_after_start_change():
        nonlocal active_start_version
        version = starts.active_path.stat().st_mtime_ns if starts.active_path.exists() else 0
        if version != active_start_version and world.elevation is not None:
            world.elevation = SimulatorElevation(root.parent)
            world.chunk.cache_clear()
            active_start_version = version

    world_routes = WorldRoutes(world, reload_after_start_change)
    workers = asyncio.Semaphore(world.settings['parallel_requests'])

    async def handle(reader, writer) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            headers = {}
            while True:
                line = await reader.readline()
                if line in HEADER_TERMINATORS:
                    break
                if b':' in line:
                    key,value=line.decode('latin-1').split(':',1)
                    headers[key.lower()]=value.strip()

            parts = request_line.decode("latin-1").split()
            if len(parts) < 2:
                return
            path = parts[1].split("?", 1)[0]
            if path == '/api/bridge' and parts[0] == 'GET':
                _write_response(writer, 200, json.dumps({'websocket_port': websocket_port}).encode(), 'application/json')
                await writer.drain()
                return
            if world_routes.handles(path):
                try:
                    body = None
                    if parts[0] == 'POST':
                        if headers.get('origin') not in (None, f"http://{headers.get('host')}"):
                            raise ValueError('Недопустимый источник запроса')
                        length = int(headers.get('content-length', '0'))
                        if not 0 < length <= WORLD_REQUEST_LIMIT_BYTES:
                            raise ValueError('Слишком большой запрос')
                        body = await asyncio.wait_for(reader.readexactly(length), 5)
                    query = parts[1].partition('?')[2]
                    if world_routes.is_tile_request(path):
                        async with workers:
                            answer = await asyncio.to_thread(world_routes.respond, parts[0], path, query, body)
                    else:
                        answer = await asyncio.to_thread(world_routes.respond, parts[0], path, query, body)
                    _write_response(writer, *answer)
                except (ValueError, TypeError, TimeoutError, asyncio.IncompleteReadError) as error:
                    _write_response(writer, 400, json.dumps({'error': str(error)}, ensure_ascii=False).encode(), 'application/json')
                await writer.drain()
                return
            if path=='/api/aircraft' and parts[0]=='POST':
                from sim_bridge.aircraft_catalog import AircraftCatalog
                from sim_bridge.custom_aircraft import create_aircraft
                try:
                    if headers.get('origin') not in (None,f"http://{headers.get('host')}"):
                        raise ValueError('Недопустимый источник запроса')
                    limit=json.loads((root.parent/'config/aircraft-import.json').read_text())['maximum_request_bytes']
                    length=int(headers.get('content-length','0'))
                    if not 0<length<=limit:raise ValueError('Файл превышает допустимый размер импорта')
                    data=json.loads(await asyncio.wait_for(reader.readexactly(length),120))
                    if not isinstance(data,dict):raise ValueError('Некорректный самолёт')
                    result=await asyncio.to_thread(create_aircraft,AircraftCatalog(root.parent),data)
                    _write_response(writer,200,json.dumps(result,ensure_ascii=False).encode(),'application/json')
                except (ValueError,TypeError,KeyError,TimeoutError) as error:
                    _write_response(writer,400,json.dumps({'error':str(error)},ensure_ascii=False).encode(),'application/json')
                await writer.drain();return
            if path=='/api/aircraft' and parts[0]=='GET':
                from sim_bridge.aircraft_catalog import AircraftCatalog
                catalog=AircraftCatalog(root.parent)
                _write_response(writer,200,json.dumps({'selected':catalog.selected()['id'],'aircraft':catalog.data['aircraft']},ensure_ascii=False).encode(),'application/json')
                await writer.drain();return
            if path=='/api/aircraft-envelope' and parts[0]=='GET':
                _write_response(writer,200,json.dumps(preferences.envelope()).encode(),'application/json')
                await writer.drain()
                return
            if path == '/api/starts':
                try:
                    if parts[0] in ('POST','DELETE'):
                        if headers.get('origin') not in (None,f"http://{headers.get('host')}"):raise ValueError('Недопустимый источник запроса')
                        length=int(headers.get('content-length','0'))
                        if not 0<length<=8192:raise ValueError('Слишком большой запрос')
                        data=json.loads(await asyncio.wait_for(reader.readexactly(length),5))
                        result=starts.delete(data.get('id')) if parts[0]=='DELETE' else starts.save(data)
                    elif parts[0]=='GET':result=starts.catalog()
                    else:raise ValueError('Метод не поддерживается')
                    _write_response(writer,200,json.dumps(result,ensure_ascii=False).encode(),'application/json')
                except (ValueError,TypeError,TimeoutError) as error:
                    _write_response(writer,400,json.dumps({'error':str(error)},ensure_ascii=False).encode(),'application/json')
                await writer.drain()
                return
            if path == '/api/training-lessons' and parts[0] == 'GET':
                lesson_file = root.parent / 'config' / 'training-lessons.json'
                _write_response(writer, 200, await asyncio.to_thread(lesson_file.read_bytes), 'application/json')
                await writer.drain()
                return
            if path == '/api/missions' and parts[0] in ('POST','DELETE'):
                try:
                    if headers.get('origin') not in (None, f"http://{headers.get('host')}"):
                        raise ValueError('Недопустимый источник запроса')
                    length = int(headers.get('content-length', '0'))
                    if not 0 < length <= 1048576:
                        raise ValueError('Слишком большой запрос')
                    data = json.loads(await asyncio.wait_for(reader.readexactly(length), 5))
                    if not isinstance(data, dict): raise ValueError('Ожидается объект миссии')
                    store = MissionStore(root.parent/'config/missions')
                    result = await asyncio.to_thread(store.delete, data.get('id')) if parts[0]=='DELETE' else await asyncio.to_thread(store.save, data.get('mission'), data.get('id'))
                    _write_response(writer, 200, json.dumps(result, ensure_ascii=False).encode(), 'application/json')
                except (ValueError, TypeError, KeyError, TimeoutError) as error:
                    _write_response(writer, 400, json.dumps({'error':str(error)}, ensure_ascii=False).encode(), 'application/json')
                await writer.drain()
                return
            if path == '/api/missions' and parts[0] == 'GET':
                catalog = await asyncio.to_thread(MissionStore.catalog, root.parent)
                _write_response(writer, 200, json.dumps(catalog, ensure_ascii=False).encode(), 'application/json')
                await writer.drain()
                return
            if path == '/api/settings':
                try:
                    if parts[0] == 'POST':
                        if headers.get('origin') not in (None, f"http://{headers.get('host')}"):
                            raise ValueError('Недопустимый источник запроса')
                        length=int(headers.get('content-length','0'))
                        if not 0<length<=8192:raise ValueError('Слишком большой запрос')
                        data=json.loads(await asyncio.wait_for(reader.readexactly(length),5))
                        preferences.save(data)
                    elif parts[0]!='GET':raise ValueError('Метод не поддерживается')
                    _write_response(writer,200,json.dumps(preferences.read()).encode(),'application/json')
                except (ValueError,TimeoutError) as error:
                    _write_response(writer,400,json.dumps({'error':str(error)},ensure_ascii=False).encode(),'application/json')
                await writer.drain()
                return
            file_path = _resolve_safely(root, path)

            if file_path is None or not file_path.is_file():
                _write_response(writer, 404, b"not found", "text/plain")
            else:
                content_type, _ = mimetypes.guess_type(str(file_path))
                _write_response(
                    writer,
                    200,
                    file_path.read_bytes(),
                    content_type or "application/octet-stream",
                )
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()

    return handle


def _resolve_safely(root: Path, url_path: str):
    """Не дать выйти за пределы каталога через ../ в адресе.

    Иначе строка вида /../../config/simulation.yaml отдала бы настройки сервера
    любому, кто открыл страницу.
    """
    if url_path in ("/", ""):
        url_path = "/index.html"

    candidate = (root / url_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _write_response(writer, status: int, body: bytes, content_type: str) -> None:
    reason = {200: "OK", 400:"Bad Request", 404: "Not Found"}.get(status, "OK")
    lines = [
        f"HTTP/1.1 {status} {reason}",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        "Cache-Control: no-cache",
        "Connection: close",
        "",
        "",
    ]
    writer.write("\r\n".join(lines).encode("latin-1") + body)
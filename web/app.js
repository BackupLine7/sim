import {setupAircraftSelector} from './aircraft-selector.js';
import {logEvent,logStatus} from './event-log.js';
import {AircraftStatus} from './aircraft-status.js';
import {setupMovablePanels} from './movable-panels.js';
import { isControlPressed } from "./control-input.mjs";
import { enableMapDragging } from "./draggable-map.mjs";
import { MissionMap } from "./mission-map.js";
import { SettingsPanel } from "./settings.js";
import { AttitudeIndicator } from "./attitude.js";
import { FlightScene } from "./scene.js";
import { TelemetryPanel } from './telemetry.js';
import { StartLocationsPanel } from './start-locations.js';
const $ = (id) => document.getElementById(id);
const telemetry = new TelemetryPanel($('telemetry-values'));
const aircraftStatus = new AircraftStatus(document.getElementById('aircraft-status'));
const settings = await fetch("/data/session.json").then((r) => r.json());
const scene = new FlightScene(settings);
window.addEventListener('streaming-settings-changed', event => {
  scene.streamingPreferences = event.detail;
  scene.world?.configure(event.detail);
});
window.addEventListener('map-grid-changed', event => {
  scene.showGrid = event.detail;
  scene.world?.setDebug(scene.showGrid);
});
enableMapDragging(document.querySelector('.map-panel'), document.querySelector('.map-title'));
const missions = new MissionMap(scene);
missions.load();
const attitude = new AttitudeIndicator();
const preferences = new SettingsPanel();
await preferences.load();
scene.loadMap().catch((error) => {
  $("notice").textContent = "Не удалось загрузить карту: " + error.message;
});
scene.setView("cockpit");
let socket,
  latest,
  displayed,
  receivedAt = 0,
  status = {},
  frames = 0,
  lastFps = performance.now(),
  previousFrame = performance.now();
const keys = new Set();
const isPressed = (key) => isControlPressed(keys, key);
const buttons = [...document.querySelectorAll("[data-action]")];
const throttle = $("throttle");
let ownsManualInput = false;
let pendingMode = null,
  lastNotice = null;

function command(action, fields = {}) {
  if (socket?.readyState !== WebSocket.OPEN) return;
  if (action === "manual") ownsManualInput = true;
  else if (action !== "stick" && action !== "speed") ownsManualInput = false;
  socket.send(JSON.stringify({ type: "command", action, ...fields }));
  if(action!=='stick')logEvent('log',`Команда: ${action} ${JSON.stringify(fields)}`);
  pendingMode =
    {
      takeoff: "TAKEOFF",
      loiter: "LOITER",
      return: "RTL",
      manual: "FBWA",
      release: "LOITER",
      land: "AUTOLAND",
      mission: "AUTO",
    }[action] || pendingMode;
  if (action !== "stick")
    $("notice").textContent =
      "Команда отправлена. Ожидаем состояние автопилота…";
}
const airspeedTarget = $("airspeed-target");
function updateSpeedControls() {
  const settings = preferences.value?.aircraft;
  const manual = status.mode === 'FBWA';
  throttle.disabled = !manual || !status.connected;
  $("throttle-help").textContent = manual ? 'Газ задаётся ползунком; скорость зависит от тяги и положения самолёта.' : `Газом управляет автопилот${status.engine_throttle_pct !== undefined ? ' · тяга '+status.engine_throttle_pct+'%' : ''}.`;
  if (settings) {
    airspeedTarget.min=settings.minimum_speed_kmh;airspeedTarget.max=Math.min(settings.maximum_speed_kmh,preferences.envelope.maximum_commanded_airspeed_kmh);
    airspeedTarget.title=`Предел задания ${preferences.envelope.model}: ${airspeedTarget.max} км/ч`;
    if (!airspeedTarget.value) airspeedTarget.value=status.target_airspeed_kmh ?? settings.cruise_speed_kmh;
  }
  $("airspeed-apply").disabled = !status.connected || status.phase !== 'flight' || !['GUIDED','AUTO','LOITER','RTL','TAKEOFF','CRUISE','FBWB'].includes(status.mode) || status.speed_pending;
  const actualSpeedKmh = latest?.airspeed_kt * 1.852;
  const speedDetails = Number.isFinite(actualSpeedKmh) ? ` · фактически ${actualSpeedKmh.toFixed(0)} км/ч` : '';
  const throttleDetails = Number.isFinite(status.engine_throttle_pct) ? ` · газ ${status.engine_throttle_pct}%` : '';
  const fullThrottle = status.engine_throttle_pct === 100 && actualSpeedKmh < status.target_airspeed_kmh
    ? '. Полный газ: дальнейший разгон зависит от тяги и условий полёта.' : '';
  $("airspeed-feedback").textContent = status.speed_pending ? 'Ожидаем подтверждения…' : status.target_airspeed_kmh ? `Задано автопилоту: ${status.target_airspeed_kmh} км/ч${speedDetails}${throttleDetails}${fullThrottle}` : 'По умолчанию используется крейсерская скорость. Максимальная — только предел.';
}
$("airspeed-apply").onclick = () => {if (airspeedTarget.reportValidity()) command('speed', {speed_kmh:airspeedTarget.valueAsNumber});};
throttle.addEventListener('input', () => {if(status.mode === 'FBWA') ownsManualInput = true;});
window.addEventListener('controls-settings-changed',updateSpeedControls);
missions.onCommand = command;
const starts = new StartLocationsPanel(scene, missions, command);
buttons.forEach(
  (button) => (button.onclick = () => command(button.dataset.action)),
);
function view(name) {
  scene.setView(name);
  $("camera-position").value = name;
  $("view-name").textContent = {
    chase: "За самолётом",
    cockpit: "Камера из носа",
    orbit: "Отладочный осмотр",
  }[name];
  $("reticle").style.display = name === "cockpit" ? "block" : "none";
  document
    .querySelectorAll("[data-view]")
    .forEach((button) =>
      button.classList.toggle("selected", button.dataset.view === name),
    );
}
document
  .querySelectorAll("[data-view]")
  .forEach((button) => (button.onclick = () => view(button.dataset.view)));
$("center").onclick = () => scene.centerMap();
scene.map.screenSpaceEventHandler.setInputAction(
  () => (scene.followMap = false),
  Cesium.ScreenSpaceEventType.LEFT_DOWN,
);
window.addEventListener("keydown", (event) => {
  if (
    event.target.matches("input,select,textarea") ||
    $("settings-dialog").open
  )
    return;
  if (
    [
      "KeyW",
      "KeyS",
      "KeyA",
      "KeyD",
      "KeyQ",
      "KeyE",
      "KeyZ",
      "KeyC",
      "ArrowUp",
      "ArrowDown",
      "ArrowLeft",
      "ArrowRight",
      "Space",
    ].includes(event.code)
  )
    event.preventDefault();
  keys.add(event.code);
  if (scene.view === 'orbit' && !['Digit1', 'Digit2', 'Digit3'].includes(event.code)) {
    keys.clear();
    return;
  }
  if (event.code === "Space") {
    keys.clear();
    command("loiter");
  }
  if (event.code === "Digit1") view("chase");
  if (event.code === "Digit2") view("cockpit");
  if (event.code === "Digit3") view("orbit");
  sendManualStick();
});
window.addEventListener("keyup", (event) => {keys.delete(event.code);sendManualStick();});
function release() {
  keys.clear();
  if (ownsManualInput) command("release");
}
window.addEventListener("blur", release);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) release();
});
for (const button of document.querySelectorAll("[data-stick]")) {
  const key = { up: "KeyW", down: "KeyS", left: "KeyA", right: "KeyD" }[
    button.dataset.stick
  ];
  button.onpointerdown = (event) => {
    button.setPointerCapture(event.pointerId);
    keys.add(key);
    sendManualStick();
  };
  button.onpointerup = button.onpointercancel = () => {keys.delete(key);sendManualStick();};
}
setInterval(() => {
  if (!throttle.disabled && isPressed("KeyQ"))
    throttle.value = Math.max(0, Number(throttle.value) - 2);
  if (!throttle.disabled && isPressed("KeyE"))
    throttle.value = Math.min(100, Number(throttle.value) + 2);
  $("throttle-value").textContent = throttle.value + "%";
  sendManualStick();
}, 100);
function sendManualStick() {
  if (ownsManualInput && status.mode === "FBWA" && !document.hidden)
    command("stick", {
      roll: preferences.axis(
        "roll",
        Number(isPressed("KeyD")) - Number(isPressed("KeyA")),
      ),
      pitch: preferences.axis(
        "pitch",
        Number(isPressed("KeyW")) - Number(isPressed("KeyS")),
      ),
      yaw: preferences.axis(
        "yaw",
        Number(isPressed("KeyC")) - Number(isPressed("KeyZ")),
      ),
      throttle: Number(throttle.value) / 100,
    });
}
throttle.addEventListener('input',sendManualStick);

let bridgeWebsocketPort = null;

async function connect() {
  if (bridgeWebsocketPort === null)
    bridgeWebsocketPort = await fetch('/api/bridge')
      .then(response => response.json())
      .then(data => data.websocket_port)
      .catch(() => Number(location.port || 80) + 1);
  socket = new WebSocket("ws://" + location.hostname + ":" + bridgeWebsocketPort);
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "control_lost") {
      logEvent('warning','Управление передано в другое окно');
      ownsManualInput = false;
      keys.clear();
      pendingMode = null;
      $("notice").textContent =
        "Управление передано в другое окно. Нажмите нужный режим, чтобы управлять здесь.";
      return;
    }
    if (message.type === "error") {
      logEvent('error',message.message);
      ownsManualInput = false;
      $("notice").textContent = message.message;
      return;
    }
    if (message.type === "status") {
      logStatus(message);
      if (
        status.generation !== undefined &&
        message.generation !== status.generation
      ) {
        latest = displayed = null;
        scene.path.length = 0;
        keys.clear();
        ownsManualInput = false;
        pendingMode = null;
        view("cockpit");
      }
      status = message;
      scene.world?.setTerrainRevision(`${status.terrain_revision}:${status.building_revision ?? 0}`);
      telemetry.update(status);
      aircraftStatus.update(status);
      starts.update(status);
      updateSpeedControls();
      missions.updateStatus(status);
      scene.airfield.update(message.phase);
      $("flight-instruction").textContent =
        {
          restarting: "Перезапуск физики. Возвращаем самолёт на ВПП…",
          preparing: "Самолёт на аэродроме. Ожидаем готовности автопилота…",
          ready: "Самолёт готов на ВПП. Нажмите «Взлететь».",
          takeoff: "Разбег и набор высоты выполняет автопилот.",
          flight:
            "Самолёт в воздухе. Летайте вручную или нажмите «Посадить на ВПП».",
          landing:
            "Автопилот выполняет заход, снижение и пробег. «Круг» отменяет посадку.",
          landed:
            "Посадка завершена, двигатель выключен. Рестарт — новое занятие.",
          crashed: "Полёт прерван аварией. Нажмите «Рестарт».",
          error: "Не удалось перезапустить самолёт. Повторите рестарт.",
        }[message.phase] || "Ожидание состояния самолёта…";
      document
        .querySelectorAll("[data-phase]")
        .forEach((item) =>
          item.classList.toggle(
            "active",
            item.dataset.phase === message.phase ||
              (message.phase === "landed" && item.dataset.phase === "landing"),
          ),
        );
      if (
        message.connected &&
        $("notice").textContent === "Соединение с симулятором…"
      )
        $("notice").textContent =
          "Самолёт подключён. Выберите режим управления.";
      $("mode").textContent = message.mode;
      $("connection").textContent = message.physics_live
        ? "Физика подключена"
        : "Нет данных физики";
      $("engine-status").textContent = message.physics_live
        ? "· живая симуляция"
        : "· нет телеметрии";
      if (pendingMode === message.mode) {
        $("notice").textContent = "Автопилот подтвердил режим " + message.mode;
        pendingMode = null;
        lastNotice = message.notice;
      } else if (message.notice && message.notice !== lastNotice) {
        $("notice").textContent = message.notice;
        lastNotice = message.notice;
      }
      buttons.forEach((button) => {
        const action = button.dataset.action;
        button.disabled =
          action === "restart"
            ? message.restarting
            : !message.connected || !message.physics_live || message.restarting;
        if (action === "takeoff")
          button.disabled ||= !["ready", "landed"].includes(message.phase);
        if (action === "land")
          button.disabled ||= !["flight", "landing"].includes(message.phase);
        if (["land", "loiter", "return", "manual"].includes(action))
          button.disabled ||= !["takeoff", "flight", "landing"].includes(
            message.phase,
          );
      });
      document
        .querySelector('[data-action="manual"]')
        .classList.toggle("selected", message.mode === "FBWA");
      return;
    }
    if (message.instance_index !== 0 || !Number.isFinite(message.latitude_deg))
      return;
    if (
      message.generation !== undefined &&
      status.generation !== undefined &&
      message.generation !== status.generation
    )
      return;
    if (status.phase === "restarting") return;
    latest = message;
    receivedAt = performance.now();
  };
  socket.onclose = () => {
    status = {};
    missions.updateStatus(status);
    buttons.forEach((button) => (button.disabled = true));
    $("connection").textContent = "Мост отключён";
    setTimeout(connect, 1500);
  };
  socket.onerror = () => {logEvent('error','Ошибка WebSocket моста');socket.close();};
  socket.addEventListener('open',()=>logEvent('log','Соединение с мостом установлено'));
  socket.addEventListener('close',()=>logEvent('warning','Соединение с мостом закрыто'));
}
buttons.forEach((button) => (button.disabled = true));
connect();
setInterval(() => {
  $("compass-needle").style.transform =
    `rotate(${-Cesium.Math.toDegrees(scene.map.camera.heading)}deg)`;
  $("map-scale").textContent = scene.navigation
    ? ((scene.followMap ? scene.navigation.height : scene.map.camera.positionCartographic.height - settings.ground_m) / 1000).toFixed(1) +
      " км · " +
      (!scene.followMap ? "обзор карты" : scene.navigation.auto ? "автомасштаб" : "ручной масштаб")
    : "Карта";
  if (!latest) return;
  $("speed").textContent = (latest.airspeed_kt * 1.852).toFixed(0);
  $("altitude").textContent = latest.altitude_agl_m.toFixed(0);
  $("heading").textContent = latest.yaw_deg.toFixed(0).padStart(3, "0");
}, 200);
function render(now) {
  if (latest && now - receivedAt < 2000) {
    if (!displayed) displayed = { ...latest };
    const blend = 1 - Math.exp(-Math.min(now - previousFrame, 100) / 60);
    for (const field of [
      "longitude_deg",
      "latitude_deg",
      "altitude_asl_m",
      "pitch_deg",
      "roll_deg",
    ])
      displayed[field] += (latest[field] - displayed[field]) * blend;
    displayed.yaw_deg +=
      (((latest.yaw_deg - displayed.yaw_deg + 540) % 360) - 180) * blend;
    displayed.ground_speed_m_s = status.ground_speed_m_s;
    displayed.airspeed_kt = latest.airspeed_kt;
    displayed.altitude_agl_m = latest.altitude_agl_m;
    scene.update(displayed);
    missions.update(displayed);
    attitude.update(displayed);
  }
  previousFrame = now;
  frames++;
  if (now - lastFps >= 1000) {
    $("render-rate").textContent =
      Math.round((frames * 1000) / (now - lastFps)) + " кадров/с";
    frames = 0;
    lastFps = now;
  }
  requestAnimationFrame(render);
}
requestAnimationFrame(render);

view("cockpit");
for (const button of document.querySelectorAll("[data-vision]"))
  button.onclick = () => {
    scene.setVision(button.dataset.vision);
    document
      .querySelectorAll("[data-vision]")
      .forEach((item) => item.classList.toggle("selected", item === button));
  };
$("day-night").onclick = () => {
  scene.setNight(!scene.night);
  $("day-night").textContent = scene.night ? "☾ Ночь → День" : "☀ День → Ночь";
};

$("camera-position").onchange = (event) => view(event.target.value);
$("camera-sensor").onchange = (event) => scene.setVision(event.target.value);
$("zoom-in").onclick = () => scene.navigation?.zoom(-1);
$("zoom-out").onclick = () => scene.navigation?.zoom(1);
$("auto-zoom").onclick = () => {
  const enabled = scene.navigation?.toggleAuto();
  $("auto-zoom").classList.toggle("selected", enabled);
};
$("toggle-controls").onclick = () => {
  $("control-body").hidden = !$("control-body").hidden;
};

preferences.onOpen = release;
window.addEventListener("controls-settings-changed", () => keys.clear());

$("map-compass").onclick = () => {
  $("map-orientation").value = "north";
  if (scene.navigation) {
    scene.navigation.orientation = "north";
    scene.navigation.heading = 0;
  }
  scene.map.camera.setView({
    orientation: { heading: 0, pitch: -Math.PI / 2, roll: 0 },
  });
};

$("map-orientation").onchange = (event) => {
  if (!scene.navigation) return;
  scene.navigation.orientation = event.target.value;
  scene.navigation.heading = event.target.value === "drone" ? (displayed?.yaw_deg ?? 0) * Math.PI / 180 : 0;
  scene.centerMap();
};
$("map-expand").onclick = () => {
  const expanded = document.querySelector('.primary').classList.toggle('map-expanded');
  $("map-expand").setAttribute('aria-expanded', String(expanded));
  $("map-expand").setAttribute('aria-label', expanded ? 'Свернуть карту' : 'Развернуть карту на половину экрана');
  $("map-expand").textContent = expanded ? '↙' : '⛶';
  requestAnimationFrame(() => { scene.main.resize(); scene.map.resize(); });
};

setupMovablePanels();

setupAircraftSelector(command);

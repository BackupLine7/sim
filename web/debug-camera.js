const C = window.Cesium;
const movementKeys = new Set(['KeyW', 'KeyS', 'KeyA', 'KeyD', 'KeyQ', 'KeyE', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ShiftLeft', 'ShiftRight']);

// One camera at render frequency; budget 0.2 ms/frame, no scratch allocations in tick.
export class DebugCamera {
  constructor(viewer, settings, getTarget) {
    this.viewer = viewer;
    this.settings = settings;
    this.getTarget = getTarget;
    this.focused = false;
    this.orbit = new C.HeadingPitchRange(0, settings.focus_pitch_rad, settings.focus_distance_m);
    this.speed = settings.speed_m_s;
    this.keys = new Set();
    this.active = false;
    this.dragging = false;
    this.direction = new C.Cartesian3();
    this.vertical = new C.Cartesian3();
    const canvas = viewer.canvas;
    canvas.tabIndex = 0;
    this.hint = document.createElement('div');
    this.hint.className = 'debug-camera-help';
    this.hint.hidden = true;
    viewer.container.append(this.hint);
    this.streamingControl=document.createElement('label');
    this.streamingControl.className='debug-camera-streaming';
    this.streamingControl.hidden=true;
    this.streamingCheckbox=document.createElement('input');
    this.streamingCheckbox.type='checkbox';
    this.streamingCheckbox.id='debug-camera-streaming';
    try { this.streamingCheckbox.checked=localStorage.getItem('flightlab-debug-camera-streaming')==='true'; } catch {}
    this.streamingCheckbox.onchange=()=>{try {localStorage.setItem('flightlab-debug-camera-streaming',String(this.streamingCheckbox.checked));}catch {}};
    this.streamingControl.append(this.streamingCheckbox,document.createTextNode(' Загружать квадраты по камере и направлению обзора'));
    viewer.container.append(this.streamingControl);
    this.updateHint();
    canvas.addEventListener('contextmenu', event => { if (this.active) event.preventDefault(); });
    canvas.addEventListener('pointerdown', event => {
      if (!this.active) return;
      canvas.focus({preventScroll:true});
      if (event.button !== 2 && !(this.focused && event.button === 0)) return;
      event.preventDefault();
      this.dragging = true;
      this.pointer = event.pointerId;
      this.x = event.clientX; this.y = event.clientY;
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', event => {
      if (!this.active || !this.dragging) return;
      const camera = viewer.camera, scale = settings.look_radians_per_pixel;
      if (this.focused) {
        this.orbit.heading += (event.clientX-this.x)*scale;
        this.orbit.pitch = C.Math.clamp(this.orbit.pitch-(event.clientY-this.y)*scale, -Math.PI/2+0.001, Math.PI/2-0.001);
      } else camera.setView({orientation: {
        heading: camera.heading + (event.clientX-this.x)*scale,
        pitch: C.Math.clamp(camera.pitch-(event.clientY-this.y)*scale, -Math.PI/2+0.001, Math.PI/2-0.001),
        roll: 0,
      }});
      this.x = event.clientX; this.y = event.clientY;
    });
    canvas.addEventListener('pointerup', () => this.releasePointer());
    canvas.addEventListener('pointercancel', () => this.reset());
    canvas.addEventListener('lostpointercapture', () => { this.dragging = false; });
    canvas.addEventListener('wheel', event => {
      if (!this.active) return;
      event.preventDefault();
      if (!event.deltaY) return;
      if (this.focused) {
        this.orbit.range = C.Math.clamp(this.orbit.range * settings.wheel_factor ** Math.sign(event.deltaY), settings.minimum_focus_distance_m, settings.maximum_focus_distance_m);
        this.updateHint();
        return;
      }
      this.speed = C.Math.clamp(this.speed * settings.wheel_factor ** -Math.sign(event.deltaY), settings.minimum_speed_m_s, settings.maximum_speed_m_s);
      this.updateHint();
    }, {passive:false});
    window.addEventListener('keydown', event => {
      if (!this.active || document.activeElement !== canvas) return;
      if (event.code === 'Enter' || event.code === 'NumpadEnter') {
        event.preventDefault();
        if (!event.repeat) this.setFocused(!this.focused);
        return;
      }
      if (!movementKeys.has(event.code)) return;
      event.preventDefault();
      if (!event.code.startsWith('Shift')) this.setFocused(false);
      this.keys.add(event.code);
    });
    window.addEventListener('keyup', event => this.keys.delete(event.code));
    canvas.addEventListener('blur', () => this.reset());
    window.addEventListener('blur', () => this.reset());
    document.addEventListener('visibilitychange', () => { if (document.hidden) this.reset(); });
    this.previousTime = performance.now();
    viewer.scene.preRender.addEventListener(() => {
      const now = performance.now();
      this.tick(Math.min((now-this.previousTime)/1000, settings.maximum_frame_s));
      this.previousTime = now;
    });
  }
  releasePointer() {
    this.dragging = false;
    if (this.pointer !== undefined && this.viewer.canvas.hasPointerCapture(this.pointer)) this.viewer.canvas.releasePointerCapture(this.pointer);
    this.pointer = undefined;
  }
  reset() { this.keys.clear(); this.releasePointer(); }
  setActive(active) {
    this.setFocused(false);
    this.active = active;
    this.reset();
    this.hint.hidden = !active;
    this.streamingControl.hidden = !active;
    if (active) this.viewer.canvas.focus({preventScroll:true});
  }
  updateHint() {
    this.hint.textContent = this.focused
      ? `Фокус на самолёте · ЛКМ/ПКМ + мышь — вращение · колесо — расстояние: ${this.orbit.range.toFixed(1)} м · Enter / WASD / стрелки — свободная камера`
      : `Enter — к самолёту · ПКМ — обзор · WASD / стрелки — движение · Q/E — вниз/вверх · Shift — ускорение · колесо — скорость: ${this.speed.toFixed(1)} м/с`;
  }
  setFocused(focused) {
    if (this.focused === focused) return;
    this.focused = focused;
    this.reset();
    if (focused) {
      this.orbit.heading = this.viewer.camera.heading;
      this.orbit.pitch = this.settings.focus_pitch_rad;
      this.orbit.range = this.settings.focus_distance_m;
      this.followTarget();
    }
    this.updateHint();
  }
  followTarget() {
    const target = this.getTarget?.();
    if (!target) return;
    this.viewer.camera.lookAt(target, this.orbit);
    // Keep world coordinates so leaving focus preserves the current view.
    this.viewer.camera.lookAtTransform(C.Matrix4.IDENTITY);
  }
  tick(delta_s) {
    if (!this.active) return;
    if (this.focused) { this.followTarget(); return; }
    if (!this.keys.size) return;
    const started = performance.now();
    const camera = this.viewer.camera, keys = this.keys;
    const forward = Number(keys.has('KeyW') || keys.has('ArrowUp'))-Number(keys.has('KeyS') || keys.has('ArrowDown'));
    const right = Number(keys.has('KeyD') || keys.has('ArrowRight'))-Number(keys.has('KeyA') || keys.has('ArrowLeft'));
    const up = Number(keys.has('KeyE'))-Number(keys.has('KeyQ'));
    C.Ellipsoid.WGS84.geodeticSurfaceNormal(camera.positionWC, this.vertical);
    this.direction.x = camera.directionWC.x*forward + camera.rightWC.x*right + this.vertical.x*up;
    this.direction.y = camera.directionWC.y*forward + camera.rightWC.y*right + this.vertical.y*up;
    this.direction.z = camera.directionWC.z*forward + camera.rightWC.z*right + this.vertical.z*up;
    if (C.Cartesian3.magnitudeSquared(this.direction) > 1e-12) {
      C.Cartesian3.normalize(this.direction, this.direction);
      camera.move(this.direction, this.speed*delta_s*(keys.has('ShiftLeft') || keys.has('ShiftRight') ? this.settings.boost_multiplier : 1));
    }
    this.lastUpdateMs = performance.now()-started;
  }
}

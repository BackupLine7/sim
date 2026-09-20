const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
export function mapHeightForSpeed(speed_m_s, settings, bias = 1) {
  return clamp(
    (settings.map_base_height_m +
      Math.max(0, speed_m_s) * settings.map_speed_lookahead_s) *
      bias,
    settings.map_min_height_m,
    settings.map_max_height_m,
  );
}
export class NavigationMap {
  constructor(scene, settings) {
    this.scene = scene;
    this.settings = settings;
    this.auto = true;
    this.orientation = "north";
    this.heading = 0;
    this.bias = 1;
    this.height = settings.map_base_height_m;
    this.target = this.height;
    this.speed = 0;
    this.lastTime = performance.now();
    scene.map.scene.screenSpaceCameraController.enableZoom = false;
    document.getElementById("map-globe").addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        event.stopPropagation();
        this.zoom(event.deltaY > 0 ? 1 : -1);
      },
      { passive: false, capture: true },
    );
  }
  zoom(direction) {
    if (!this.scene.followMap) {
      this.target = this.scene.map.camera.positionCartographic.height - this.scene.settings.ground_m;
    }
    const factor = this.settings.map_zoom_factor ** direction;
    this.bias = clamp(this.bias * factor, 0.15, 8);
    this.target = clamp(
      this.target * factor,
      this.settings.map_min_height_m,
      this.settings.map_max_height_m,
    );
    if (!this.scene.followMap) {
      this.height = this.target;
      const p = this.scene.map.camera.positionCartographic;
      this.scene.map.camera.setView({
        destination: Cesium.Cartesian3.fromRadians(
          p.longitude,
          p.latitude,
          this.scene.settings.ground_m + this.height,
        ),
      });
    }
  }
  toggleAuto() {
    this.auto = !this.auto;
    if (this.auto) this.bias = 1;
    else this.target = this.height;
    return this.auto;
  }
  update(pose) {
    this.heading = this.orientation === "drone" ? pose.yaw_deg * Math.PI / 180 : 0;
    const now = performance.now(),
      dt = Math.min((now - this.lastTime) / 1000, 0.1);
    this.lastTime = now;
    this.speed = pose.ground_speed_m_s ?? pose.airspeed_kt * 0.514444;
    if (this.auto)
      this.target = mapHeightForSpeed(this.speed, this.settings, this.bias);
    this.height +=
      (this.target - this.height) *
      (1 - Math.exp(-dt / this.settings.map_zoom_response_s));
    if (this.scene.followMap) this.scene.centerMap();
  }
}

const C = window.Cesium;
export class AirfieldView {
  constructor(scene) {
    this.scene = scene;
    const settings = scene.settings,
      airfield = settings.airfield;
    if (!airfield) return;
    this.airfield = airfield;
    this.heading = (settings.heading_deg * Math.PI) / 180;
    const surface = (points, material, height = 0.15) =>
      scene.main.entities.add({
        polygon: {
          hierarchy: C.Cartesian3.fromDegreesArray(points.flat()),
          height: settings.ground_m + height,
          material,
        },
      });
    const rectangle = (start, end, left, right, material, height) =>
      surface(
        [
          this.offset(start, left),
          this.offset(end, left),
          this.offset(end, right),
          this.offset(start, right),
        ],
        material,
        height,
      );
    const start = -airfield.start_from_threshold_m,
      end = start + airfield.runway_length_m,
      half = airfield.runway_width_m / 2;
    rectangle(
      start - 20,
      end + 20,
      -half - 10,
      half + 10,
      C.Color.fromCssColorString("#6b7452"),
      0.1,
    );
    rectangle(
      start,
      end,
      -half,
      half,
      C.Color.fromCssColorString("#44494b"),
      0.16,
    );
    for (const side of [-1, 1])
      rectangle(
        start,
        end,
        side * (half - 1) - 0.25,
        side * (half - 1) + 0.25,
        C.Color.WHITE,
        0.2,
      );
    for (let distance = start + 100; distance < end - 80; distance += 70)
      rectangle(distance, distance + 30, -0.65, 0.65, C.Color.WHITE, 0.2);
    for (const threshold of [start + 8, end - 35])
      for (let lateral = -half + 5; lateral < half - 3; lateral += 4)
        rectangle(
          threshold,
          threshold + 25,
          lateral,
          lateral + 1.8,
          C.Color.WHITE,
          0.2,
        );
    const outline = [
      this.offset(start, -half),
      this.offset(end, -half),
      this.offset(end, half),
      this.offset(start, half),
      this.offset(start, -half),
    ];
    scene.map.entities.add({
      polyline: {
        positions: C.Cartesian3.fromDegreesArrayHeights(
          outline.flatMap((p) => [...p, settings.ground_m + 1]),
        ),
        width: 3,
        material: C.Color.WHITE,
      },
    });
    scene.map.entities.add({
      position: C.Cartesian3.fromDegrees(
        ...settings.home,
        settings.ground_m + 1,
      ),
      label: {
        text: "ВПП 09 · Полтава",
        font: "12px sans-serif",
        pixelOffset: new C.Cartesian2(0, 20),
        fillColor: C.Color.WHITE,
        showBackground: true,
      },
    });
    const approach = this.offset(-airfield.parameters.AUTOLAND_WP_DIST, 0);
    this.approach = scene.map.entities.add({
      show: false,
      polyline: {
        positions: C.Cartesian3.fromDegreesArrayHeights([
          ...approach,
          settings.ground_m + airfield.parameters.AUTOLAND_WP_ALT,
          ...settings.home,
          settings.ground_m + 1,
        ]),
        width: 3,
        material: C.Color.ORANGE,
      },
    });
  }
  offset(forward, right) {
    const [longitude, latitude] = this.scene.settings.home;
    const north =
      Math.cos(this.heading) * forward - Math.sin(this.heading) * right;
    const east =
      Math.sin(this.heading) * forward + Math.cos(this.heading) * right;
    return [
      longitude + east / (111320 * Math.cos((latitude * Math.PI) / 180)),
      latitude + north / 111320,
    ];
  }
  update(phase) {
    if (this.approach) this.approach.show = phase === "landing";
  }
}

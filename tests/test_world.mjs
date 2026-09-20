import assert from "node:assert/strict";
import { aircraftBasis } from "../web/flight-math.mjs";
import { nearbyTiles } from "../web/world/coverage.mjs";
import fs from "node:fs";
const settings = JSON.parse(
  fs
    .readFileSync(new URL("../config/world.json", import.meta.url), "utf8")
    .replace(/^\uFEFF/, ""),
);
delete settings.distant_terrain_level; // Existing detailed-neighbourhood contract.
let basis = aircraftBasis(0, 0, Math.PI / 6);
assert.ok(basis.right[2] < 0, "right bank lowers right wing");
assert.ok(basis.up[0] > 0, "right bank tilts camera up axis right");
basis = aircraftBasis(Math.PI / 2, 0, 0);
assert.ok(Math.abs(basis.forward[0] - 1) < 1e-9, "east heading faces east");
assert.ok(aircraftBasis(0, 0.2, 0).forward[2] > 0, "positive pitch points up");
assert.equal(nearbyTiles(30.5234, 50.4501, settings).length, 9);
const { WorldStreamer } = await import("../web/world/streamer.js");
const streamer = new WorldStreamer({}, settings);
streamer.pump = () => {};
streamer.update({ longitude_deg: 30.5234, latitude_deg: 50.4501 });
let destroyed = 0;
for (const key of streamer.desired)
  streamer.resident.set(key, {
    tile: {
      setVisible() {},
      destroy() {
        destroyed++;
      },
    },
  });
streamer.lastUpdate = -1000;
streamer.update({ longitude_deg: 36.23, latitude_deg: 49.99 });
assert.equal(destroyed, 9, "leaving region destroys all old resources");
assert.equal(streamer.resident.size, 0);
assert.equal(streamer.desired.size, 9);
const wanted = [...streamer.desired];
streamer.host.camera = { longitude_deg: 40, latitude_deg: 52 };
streamer.lastUpdate = -1000;
streamer.update({ longitude_deg: 36.23, latitude_deg: 49.99 });
assert.deepEqual(
  [...streamer.desired],
  wanted,
  "camera cannot move loading anchor",
);
streamer.lastUpdate = -1000;
streamer.update({ longitude_deg: 0, latitude_deg: 0 });
assert.equal(
  streamer.desired.size,
  0,
  "outside configured region unloads terrain",
);
console.log(
  "PASS camera basis, bounded neighbourhood, resource eviction, camera-independent loading, region exit",
);
const deferred = [];
const queued = new WorldStreamer({}, settings);
queued.load = (key) =>
  new Promise((resolve) => deferred.push({ key, resolve }));
queued.update({ longitude_deg: 30.5234, latitude_deg: 50.4501 });
assert.equal(queued.pending.size, 2, "parallel requests are bounded");
queued.lastUpdate = -Infinity;
queued.update({ longitude_deg: 36.23, latitude_deg: 49.99 });
assert.ok(
  [...queued.pending.values()].every((controller) => controller.signal.aborted),
  "obsolete requests aborted",
);
assert.equal(
  queued.pending.size,
  2,
  "aborting does not prematurely release request slots",
);
queued.desired.clear();
for (const request of deferred) request.resolve();
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(queued.pending.size, 0);
console.log("PASS request backpressure and cancellation");
import { mapHeightForSpeed } from "../web/navigation-map.mjs";
assert.ok(
  mapHeightForSpeed(25, settings) > mapHeightForSpeed(0, settings),
  "faster flight shows a larger area",
);
assert.ok(
  mapHeightForSpeed(25, settings, 0.5) < mapHeightForSpeed(25, settings),
  "manual zoom adjusts auto framing",
);
assert.equal(mapHeightForSpeed(100000, settings), settings.map_max_height_m);
assert.equal(mapHeightForSpeed(0, settings, 0.01), settings.map_min_height_m);
console.log("PASS navigation speed zoom and bounds");
import { isControlPressed } from "../web/control-input.mjs";
const held = new Set(["KeyA", "ArrowLeft"]);
assert.equal(isControlPressed(held, "KeyA"), true);
held.delete("KeyA");
assert.equal(
  isControlPressed(held, "KeyA"),
  true,
  "releasing A must not release held Left",
);
held.delete("ArrowLeft");
assert.equal(isControlPressed(held, "KeyA"), false);
held.add("ArrowUp");
assert.equal(isControlPressed(held, "KeyW"), true);
console.log("PASS simultaneous WASD and arrows");
import { visualGroundCorrection } from "../web/model-alignment.mjs";
const support = JSON.parse(
  fs.readFileSync(
    new URL("../web/data/aircraft-support.json", import.meta.url),
    "utf8",
  ),
).support_points;
const groundPose = { altitude_agl_m: 0.382, pitch_deg: 14, roll_deg: 0 };
const lift = visualGroundCorrection(groundPose, settings, support);
const pitch = (14 * Math.PI) / 180;
for (const point of support) {
  const height =
    0.382 +
    settings.aircraft_visual_origin_up_m * Math.cos(pitch) +
    lift +
    settings.aircraft_visual_scale *
      (point[0] * Math.sin(pitch) + point[2] * Math.cos(pitch));
  assert.ok(
    height >= settings.runway_visual_height_m - 1e-8,
    "model must not penetrate runway",
  );
}
assert.equal(
  visualGroundCorrection(
    { ...groundPose, altitude_agl_m: 100 },
    settings,
    support,
  ),
  0,
  "alignment must not change flight dynamics or airborne pose",
);
console.log("PASS model ground clearance");

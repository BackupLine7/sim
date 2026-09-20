# Interactive simulator baseline

Five configured aircraft; one active workstation initially. UDP poses feed a
latest-state buffer. Rendering is capped at 60 FPS (16.67 ms budget), control
inputs at 10 Hz, telemetry labels at 5 Hz. Budget targets require measurement
on the eventual training hardware. Browser render time is not simulation time.

The MAVLink adapter owns its connection on one worker thread. A bounded command
queue and replaceable latest RC input prevent growing queues. Only named
commands are accepted. The renderer depends on pose messages, not MAVLink.
Network JSON allocation is acceptable at these rates; avoid per-packet render.
Missing physics must be shown explicitly, never silently replaced by a replay.

Initial map: locally packaged OpenStreetMap extract (ODbL, attribution visible).
Buildings use mapped footprints and approximate heights. It is not an orthophoto
or collision mesh. A separate training airfield remains to be added.
DEM integration, five-student endurance, and exact collision terrain remain
separate acceptance gates. No third-party source changes are permitted.

Verification: malformed/unknown command rejection, real MAVLink mode changes,
takeoff with finite state, bounded client stream, browser render and input QA.

## Verified 2026-09-10

- Six command/pose boundary tests and four existing terrain limiter tests pass.
- Live browser buttons: TAKEOFF climbed to 150 m, LOITER confirmed, FBWA and
  throttle slider changed the flight, FBWA -> RTL confirmed after fixing stale
  RC cleanup overriding the requested mode.
- Local map, 3D buildings and Cesium aircraft sample visually verified.
- Browser animation loop reported 60 updates/s on this machine. This is not a
  GPU p99 measurement or a five-workstation performance certification.
- Runtime uses isolated build/sessions/0. Cause of the previous long-flight
  crash is not established; current smoke flight does not prove endurance.

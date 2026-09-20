# Full flight session

One existing SITL + JSBSim instance; physics remains unchanged. A SessionRuntime
adapter owns only the configured Docker container. Restart is explicit, has a
30 s timeout and clears the simulated vehicle state. Pose/heartbeat reconnect
asynchronously, UI resets its trail by generation and waits for fresh physics.
Flight control queue remains bounded at 8. No subprocess on render/UDP hot paths.
Session classification is O(1) per pose, target <0.1 ms, no history buffer.

Airfield home/heading/elevation: simulation.yaml is the source of truth.
Runway dimensions and training parameters: airfield.json. Visual runway is
placed relative to that home. Terrain remains flat at the configured elevation.
Historical civilian UKHP diagram: threshold 09 49°34′14″N 34°22′36″E,
true heading 96.15°, 2550 x 42 m. Home/touchdown is 250 m after the threshold.

Stages: restarting -> preparing -> ready -> takeoff -> flight -> landing ->
landed. These follow live FDM and heartbeat, not button clicks. Landing requires
low height, stopped aircraft, disarm, and a previous flight; ground at startup
is not a successful landing. Crash notices/failure/timeouts stay visible.

ArduPlane 4.7.1 includes AUTOLAND: capture direction at arming, loiter-to-alt,
final approach, flare and rollout. Use this upstream mode through our adapter;
no duplicate landing controller and no third-party changes. RTL remains return
and circle. Abort landing switches to LOITER; restart works even disconnected.

Validation (2026-09-10): restart, readiness, takeoff, flight, AUTOLAND touchdown,
stop and disarm completed in an isolated SITL instance. Runway containment still
fails: the latest rollout stopped 29.1 m from the centreline of the 42 m runway.
The `landed` phase currently confirms a stopped/disarmed aircraft, not a graded
successful runway landing. Ground steering needs further calibration.

Interface verification: 19 Python tests passed; browser-module checks passed for
parallel WASD/arrows, map speed zoom, bounded tile streaming and model clearance.
The soft monochrome sensor is a visual effect, not a temperature simulation.

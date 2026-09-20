# Local example map

OpenStreetMap API extract downloaded 2026-09-10, bbox
30.51,50.445,30.535,50.455. © OpenStreetMap contributors, ODbL.
https://www.openstreetmap.org/copyright

`kyiv.osm` is the source; `python scripts/prepare_example_map.py` rebuilds
`kyiv.svg` and `map.json`. This is a cartographic map, not an orthophoto.
Building heights default to 12.8 m when the extract has no height/levels.
Buildings are visual only; JSBSim does not collide with these meshes.

`aircraft.glb`: Cesium_Air sample, copied unmodified from the pinned CesiumJS
1.145 submodule. Copyright CesiumJS Contributors, Apache 2.0 (included in
CESIUM-LICENSE.md). This visual is illustrative; the FDM remains Rascal.

# Local imagery cache

Source: Sentinel-2 cloudless 2016, EOX IT Services GmbH.
Contains modified Copernicus Sentinel data 2016 & 2017.
License: Creative Commons Attribution 4.0 International (CC BY 4.0).
https://maps.eox.at/ — https://s2maps.eu

Historical composite, not current imagery. Downloaded via public WMTS using
scripts/prepare_world.py. See config/world.json for coverage and fixed source.
Cache contains 225 overview z9 tiles and 45 detailed z14 example tiles.
The renderer falls back to the overview where detailed data are absent.
No network requests are required during a lesson.

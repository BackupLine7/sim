"""Prepare the local DEM used by both the visual mesh and physical terrain."""
import gzip,json,urllib.request
from pathlib import Path
import rasterio
import yaml
ROOT=Path(__file__).resolve().parents[1]
settings=json.loads((ROOT/'config/terrain-preparation.json').read_text())
simulation=yaml.safe_load((ROOT/'config/simulation.yaml').read_text(encoding='utf-8'))
source=ROOT/settings['source_path']
source.parent.mkdir(parents=True,exist_ok=True)
if not source.exists():
    with urllib.request.urlopen(settings['source_url'],timeout=settings['timeout_s']) as response:
        source.write_bytes(gzip.decompress(response.read()))
target=ROOT/simulation['terrain']['dem_path']
with rasterio.open(source) as dataset:
    profile=dataset.profile.copy()
    profile.update(driver='GTiff',compress='deflate')
    with rasterio.open(target.with_suffix('.tmp.tif'),'w',**profile) as output:
        output.write(dataset.read())
target.with_suffix('.tmp.tif').replace(target)
print(f'Prepared {target}')

"""Build the bundled region list; normal simulator startup never fetches it."""
import concurrent.futures
import json
from pathlib import Path
import urllib.request

from shapely.geometry import shape, box

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT/'config/building-regions.json').read_text())
WORLD = json.loads((ROOT/'config/world.json').read_text(encoding='utf-8-sig'))
DIRECTORY = ROOT/CONFIG['directory']
DIRECTORY.mkdir(parents=True, exist_ok=True)


def read(url):
    with urllib.request.urlopen(url, timeout=CONFIG['http_timeout_s']) as response:
        return json.load(response)


def country_regions(country):
    metadata = read(CONFIG['boundary_api'].format(country=country))
    url = metadata['gjDownloadURL'].replace('https://github.com/', 'https://media.githubusercontent.com/media/').replace('/raw/', '/')
    path = DIRECTORY/f'boundary-{country}.json'
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else read(url)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    regions = []
    for feature in data['features']:
        geometry = shape(feature['geometry'])
        if not geometry.intersects(box(*WORLD['bounds'])):
            continue
        properties = feature['properties']
        regions.append(dict(id='gb-'+properties['shapeID'], name=properties['shapeName'], country=country,
                            code=properties['shapeISO'], bounds=list(geometry.bounds),
                            boundary_url=url, boundary_id=properties['shapeID']))
    print(country, len(regions), flush=True)
    return regions


def main():
    countries = read(CONFIG['country_boundaries_url'])
    codes = set()
    country_codes = {}
    for feature in countries['features']:
        if shape(feature['geometry']).intersects(box(*WORLD['bounds'])):
            code = feature['properties']['ADM0_A3']
            code = 'XKX' if code == 'KOS' else code
            codes.add(code)
            country_codes[code] = feature['properties']['ISO_A2_EH'] if code != 'XKX' else 'XK'
    regions = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['catalog_workers']) as pool:
        jobs = {pool.submit(country_regions, code):code for code in codes}
        errors = []
        for job in concurrent.futures.as_completed(jobs):
            try:
                regions.extend(job.result())
            except Exception as error:
                errors.append((jobs[job],str(error)))
    if errors:
        raise RuntimeError(errors)
    names = json.loads((ROOT/'config/building-region-names.json').read_text(encoding='utf-8'))
    for region in regions:
        region['boundary_country'] = region['country']
        region['country'] = country_codes[region['country']]
        region['name'] = names.get(region['code'], region['name'])
    catalog = dict(bounds=WORLD['bounds'], regions=sorted(regions, key=lambda r: (r['country'] != 'UA', r['country'], r['name'])))
    path = ROOT/CONFIG['region_catalog']
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Saved', len(regions), flush=True)


if __name__ == '__main__':
    main()

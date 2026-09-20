"""Convert the bundled OSM extract to a local SVG map and building footprints."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'web' / 'data'

def main():
    root = ET.parse(DATA / 'kyiv.osm').getroot()
    bounds = [30.51, 50.445, 30.535, 50.455]
    west, south, east, north = bounds
    nodes = {n.attrib['id']: (float(n.attrib['lon']), float(n.attrib['lat'])) for n in root.findall('node')}
    def point(coord):
        lon, lat = coord
        return f'{(lon-west)/(east-west)*2048:.2f},{(north-lat)/(north-south)*1280:.2f}'
    layers = [[], [], []]
    buildings = []
    for way in root.findall('way'):
        tags = {t.attrib['k']: t.attrib['v'] for t in way.findall('tag')}
        coords = [nodes[n.attrib['ref']] for n in way.findall('nd') if n.attrib['ref'] in nodes]
        if len(coords) < 2:
            continue
        points = ' '.join(map(point, coords))
        if 'building' in tags and coords[0] == coords[-1]:
            layers[1].append(f'<polygon points="{points}" fill="#b5afa0" stroke="#918c7e" stroke-width="1"/>')
            try:
                height = float(tags.get('height', float(tags.get('building:levels', 4))*3.2))
            except ValueError:
                height = 12.8
            if all(west <= x <= east and south <= y <= north for x, y in coords):
                buildings.append({'coordinates': coords, 'height_m': min(80, max(3, height))})
        elif 'highway' in tags:
            width = 8 if tags['highway'] in ('primary', 'secondary', 'tertiary') else 3
            layers[2].append(f'<polyline points="{points}" fill="none" stroke="#e8dfc9" stroke-width="{width}" stroke-linejoin="round"/>')
        elif coords[0] == coords[-1] and ('landuse' in tags or 'natural' in tags or 'leisure' in tags):
            color = '#5d939d' if tags.get('natural') == 'water' else '#7c9569'
            layers[0].append(f'<polygon points="{points}" fill="{color}"/>')
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="2048" height="1280" viewBox="0 0 2048 1280"><rect width="2048" height="1280" fill="#9ea68a"/>' + ''.join(''.join(layer) for layer in layers) + '</svg>'
    (DATA / 'kyiv.svg').write_text(svg, encoding='utf-8')
    (DATA / 'map.json').write_text(json.dumps({'bounds': bounds, 'buildings': buildings, 'credit': '© OpenStreetMap contributors · ODbL', 'source': 'https://www.openstreetmap.org/copyright'}), encoding='utf-8')
    print(f'Local map prepared: {len(buildings)} buildings')

if __name__ == '__main__':
    main()

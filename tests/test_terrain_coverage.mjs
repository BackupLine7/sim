import assert from 'node:assert/strict';
import {terrainCoverage,terrainCoverageForPositions,nearbyTiles} from '../web/world/coverage.mjs';
const settings = {detail_level:14, active_radius_tiles:1, max_resident_tiles:9,
  distant_terrain_level:10, distant_terrain_radius_tiles:2};
const keys = terrainCoverage(34.69,45.27,settings);
const near = nearbyTiles(34.69,45.27,settings);
assert.ok(near.every(key => keys.includes(key)));
const selected = new Set(keys);
let area = 0;
for (const key of keys) {
  let [z,x,y] = key.split('/').map(Number);
  area += 4 ** (10-z);
  while (z > 10) {
    z--; x=Math.floor(x/2); y=Math.floor(y/2);
    assert.ok(!selected.has(`${z}/${x}/${y}`), 'No coarse terrain overlaps a detailed building tile');
  }
}
assert.equal(area,25,'Refinement leaves no holes in the far terrain');
assert.ok(keys.length<100,'Far terrain does not multiply full-detail loads');
console.log('PASS far terrain coverage, no overlap, no holes, bounded tile count');
const cameras=[{longitude_deg:34.69,latitude_deg:45.27},{longitude_deg:34.75,latitude_deg:45.3}];
const combined=new Set(terrainCoverageForPositions(cameras,settings));
for(const point of cameras)for(const key of nearbyTiles(point.longitude_deg,point.latitude_deg,settings))assert.ok(combined.has(key));
for(const key of combined){let [z,x,y]=key.split('/').map(Number);while(z>settings.distant_terrain_level){z--;x=Math.floor(x/2);y=Math.floor(y/2);assert.ok(!combined.has(`${z}/${x}/${y}`));}}
assert.deepEqual(terrainCoverageForPositions([],settings),[]);
console.log('PASS camera and view target coverage without overlapping levels');

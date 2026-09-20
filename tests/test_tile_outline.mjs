import assert from 'node:assert/strict';
import {tileOutlinePositions} from '../web/world/outline.mjs';

const positions=tileOutlinePositions({bounds:[10,20,12,22],terrain:{size:3,latitudes:[22,21,20],
  heights_m:[100,500,110,200,9999,210,120,600,130]}},-100,3);
assert.equal(positions.length,27);
assert.deepEqual(positions.slice(0,3),positions.slice(-3),'Boundary is closed');
assert.ok(positions.includes(503),'Northern hill is followed');
assert.ok(positions.includes(603),'Southern hill is followed');
assert.ok(!positions.includes(10002),'Interior sample does not become a grid edge');
assert.ok(!positions.includes(-97),'Terrain heights replace the home altitude');
const flat=tileOutlinePositions({bounds:[10,20,12,22]},50,3);
assert.equal(flat.length,15);
assert.equal(flat[2],53);
console.log('PASS terrain-following tile outlines');

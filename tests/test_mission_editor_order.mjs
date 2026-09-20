import assert from 'node:assert/strict';
import {missionHeightM} from '../web/mission-height.mjs';
globalThis.window={Cesium:{}};
const {MissionEditor}=await import('../web/mission-editor.js');
const a={name:'A'},b={name:'B'},c={name:'C'};
const editor=Object.assign(Object.create(MissionEditor.prototype),{
  draft:{waypoints:[a,b,c]},index:1,editPoint(){},render(){}
});
editor.reorder(-1);
assert.deepEqual(editor.draft.waypoints,[b,a,c]);
assert.equal(editor.index,0);
editor.reorder(-1);
assert.deepEqual(editor.draft.waypoints,[b,a,c]);
editor.reorder(1);
assert.deepEqual(editor.draft.waypoints,[a,b,c]);
assert.equal(editor.index,1);
assert.equal(missionHeightM({type:'goal',altitude_relative_m:700,terrain_elevation_asl_m:300},900),300);
assert.ok(Number.isNaN(missionHeightM({type:'goal',altitude_relative_m:700},900)));
assert.equal(missionHeightM({type:'transit',altitude_relative_m:700},900),1600);
console.log('Mission reorder and terrain goal heights passed');

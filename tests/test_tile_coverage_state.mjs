import assert from 'node:assert/strict';
import {visibleLoadedTiles} from '../web/world/tile-keys.mjs';
const parent='10/2/3',children=['11/4/6','11/5/6','11/4/7','11/5/7'];
assert.deepEqual([...visibleLoadedTiles(new Set(children),new Set([parent,children[0]]))],[parent],'Partial refinement must keep the complete parent');
assert.deepEqual(visibleLoadedTiles(new Set(children),new Set([parent,...children])),new Set(children),'Switch only when replacement is complete');
assert.deepEqual(visibleLoadedTiles(new Set([parent]),new Set(children)),new Set(children),'Keep children until the coarse tile arrives');
assert.deepEqual(visibleLoadedTiles(new Set([parent]),new Set([parent,...children])),new Set([parent]),'Never draw parent over children');
console.log('PASS continuous coverage during refinement and coarsening');

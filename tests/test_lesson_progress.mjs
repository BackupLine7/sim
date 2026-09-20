import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {LessonProgress, TYPE_LABELS} from '../web/training/lesson-progress.mjs';
const {lessons}=JSON.parse(readFileSync(new URL('../config/training-lessons.json',import.meta.url),'utf8'));
assert.equal(lessons.length,15);
assert.equal(new Set(lessons.map(lesson=>lesson.id)).size,15);
for(const lesson of lessons){
  assert.equal(lesson.coordinate_system,'fictional_local');
  const progress=new LessonProgress(lesson);
  assert.equal(progress.update(lesson.waypoints.at(-1)),false,'Cannot skip ahead');
  const first=lesson.waypoints[0];
  assert.equal(progress.update({...first,height_m:first.height_m+lesson.height_tolerance_m+1}),false,'Wrong height must not pass');
  for(const [index,point] of lesson.waypoints.entries()){
    assert.ok(TYPE_LABELS[point.type]);
    assert.equal(progress.update(point),true);
    assert.equal(progress.next,index+1);
    if(index>0) assert.equal(progress.segmentComplete(index-1),true);
    if(index<lesson.waypoints.length-1) assert.equal(progress.segmentComplete(index),false);
  }
  assert.equal(progress.complete,true);
  assert.equal(progress.update(lesson.waypoints.at(-1)),false);
  assert.equal(new LessonProgress(lesson).next,0);
}
console.log('PASS 15 fictional lessons: ordered gates, height tolerance, completed segments and reset');

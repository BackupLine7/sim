import {LessonProgress, TYPE_LABELS} from './lesson-progress.mjs';
import {missionPointColor, MISSION_COLORS} from '../mission-colors.mjs';
const $ = id => document.getElementById(id);
const map = $('map'), camera = $('camera');
let lessons = [], lesson, progress, position, heading = 0, running = false, previousTime;
const keys = new Set();
const preferencesKey = 'flightlab-fictional-lesson-hints';
let hints = {arrows:true, zones:true};
try { Object.assign(hints, JSON.parse(localStorage.getItem(preferencesKey) || '{}')); } catch {}
$('show-arrows').checked = hints.arrows;
$('show-zones').checked = hints.zones;
for (const [id,key] of [['show-arrows','arrows'],['show-zones','zones']]) $(id).onchange = event => {
  hints[key] = event.target.checked;
  try {localStorage.setItem(preferencesKey, JSON.stringify(hints));} catch {}
};
$('settings').onclick = () => {setRunning(false); $('options').showModal();};
function setRunning(value) {running=value; $('pause').textContent=running?'Ⅱ Пауза':'▶ Начать';}
function reset() {
  lesson=lessons.find(item=>item.id===$('lesson').value);
  progress=new LessonProgress(lesson);
  position={...lesson.start}; heading=0; keys.clear(); setRunning(false);
  $('movement').value='route';
  $('points').replaceChildren(...lesson.waypoints.map((point,index)=>{
    const row=document.createElement('li'); row.textContent=`${index+1}. ${TYPE_LABELS[point.type]} · ${point.name} · ${point.height_m} м`;
    return row;
  }));
  updateStatus();
}
function updateStatus() {
  $('progress').textContent=progress.complete?'Занятие завершено':`Пройдено ${progress.next} / ${lesson.waypoints.length}`;
  $('instruction').textContent=progress.complete?'Все учебные области пройдены. Выберите следующее занятие.':`Следующая: ${TYPE_LABELS[lesson.waypoints[progress.next].type]} — ${lesson.waypoints[progress.next].name}`;
  [...$('points').children].forEach((row,index)=>{row.className=index<progress.next?'done':index===progress.next?'active':'';row.style.color=missionPointColor(index,progress.next);});
}
$('lesson').onchange=reset;
$('restart').onclick=reset;
$('pause').onclick=()=>setRunning(!running && !progress.complete);
window.addEventListener('keydown',event=>{
  if ($('options').open || event.target.matches('input,select')) return;
  if (['KeyW','KeyS','KeyA','KeyD','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.code)) {event.preventDefault();keys.add(event.code);}
});
window.addEventListener('keyup',event=>keys.delete(event.code));
window.addEventListener('blur',()=>{keys.clear();setRunning(false);});
document.addEventListener('visibilitychange',()=>{if(document.hidden)setRunning(false);});

function advance(dt) {
  if (!running || progress.complete) return;
  const point=lesson.waypoints[progress.next], speed=lesson.demo_speed_m_s;
  if ($('movement').value==='route') {
    // Constant-speed lesson playback, deliberately separate from flight dynamics.
    const dx=point.x_m-position.x_m,dy=point.y_m-position.y_m,dh=point.height_m-position.height_m;
    const distance=Math.hypot(dx,dy,dh), fraction=Math.min(1,speed*dt/Math.max(distance,.001));
    if (Math.hypot(dx,dy)>1) heading=Math.atan2(dx,dy);
    position.x_m+=dx*fraction;position.y_m+=dy*fraction;position.height_m+=dh*fraction;
  } else {
    if ($('movement').value==='manual') {
      heading+=((keys.has('KeyD')||keys.has('ArrowRight'))-(keys.has('KeyA')||keys.has('ArrowLeft')))*dt;
      position.height_m=Math.max(0,position.height_m+((keys.has('KeyW')||keys.has('ArrowUp'))-(keys.has('KeyS')||keys.has('ArrowDown')))*40*dt);
    }
    position.x_m+=Math.sin(heading)*speed*dt;position.y_m+=Math.cos(heading)*speed*dt;
  }
  if(progress.update(position)) {updateStatus();if(progress.complete)setRunning(false);}
}
function context(canvas) {
  const width=canvas.clientWidth,height=canvas.clientHeight,dpr=Math.min(devicePixelRatio,2);
  if(canvas.width!==Math.round(width*dpr)||canvas.height!==Math.round(height*dpr)){canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);}
  const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);return {ctx,width,height};
}
function drawMap() {
  const {ctx,width,height}=context(map);
  ctx.fillStyle='#132f33';ctx.fillRect(0,0,width,height);
  const points=[...lesson.waypoints,lesson.start,position];
  const minX=Math.min(...points.map(p=>p.x_m))-150,maxX=Math.max(...points.map(p=>p.x_m))+150;
  const minY=Math.min(...points.map(p=>p.y_m))-150,maxY=Math.max(...points.map(p=>p.y_m))+150;
  const scale=Math.min((width-50)/(maxX-minX),(height-50)/(maxY-minY));
  const xy=p=>[width/2+(p.x_m-(minX+maxX)/2)*scale,height/2-(p.y_m-(minY+maxY)/2)*scale];
  ctx.strokeStyle='#24464a';ctx.lineWidth=1;ctx.setLineDash([]);
  for(let x=0;x<width;x+=40){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();}
  for(let y=0;y<height;y+=40){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();}
  lesson.waypoints.forEach((point,index)=>{
    const [x,y]=xy(point);
    if(index){const [a,b]=xy(lesson.waypoints[index-1]);ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(x,y);ctx.lineWidth=3;ctx.strokeStyle=missionPointColor(index,progress.next);ctx.setLineDash(progress.segmentComplete(index-1)?[]:[7,6]);ctx.stroke();}
    ctx.setLineDash([]);ctx.beginPath();ctx.arc(x,y,Math.max(7,point.radius_m*scale),0,Math.PI*2);ctx.fillStyle=missionPointColor(index,progress.next)+'25';ctx.fill();ctx.strokeStyle=missionPointColor(index,progress.next);ctx.lineWidth=2;ctx.stroke();
    if(index===progress.next && point.type==='goal'){ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fillStyle=MISSION_COLORS.goal;ctx.fill();}
    ctx.fillStyle=ctx.strokeStyle;ctx.font='bold 12px sans-serif';ctx.fillText(String(index+1),x+10,y-10);
  });
  const [x,y]=xy(position);ctx.save();ctx.translate(x,y);ctx.rotate(heading);ctx.beginPath();ctx.moveTo(0,-12);ctx.lineTo(8,10);ctx.lineTo(0,6);ctx.lineTo(-8,10);ctx.closePath();ctx.fillStyle='#fff';ctx.fill();ctx.restore();
}
function drawCamera() {
  const {ctx,width,height}=context(camera), horizon=height*.46, focal=width*.75;
  const sky=ctx.createLinearGradient(0,0,0,horizon);sky.addColorStop(0,'#315c70');sky.addColorStop(1,'#a9d1ce');ctx.fillStyle=sky;ctx.fillRect(0,0,width,horizon);
  const ground=ctx.createLinearGradient(0,horizon,0,height);ground.addColorStop(0,'#6f9180');ground.addColorStop(1,'#203d36');ctx.fillStyle=ground;ctx.fillRect(0,horizon,width,height-horizon);
  function project(point) {
    const dx=point.x_m-position.x_m,dy=point.y_m-position.y_m;
    const forward=dx*Math.sin(heading)+dy*Math.cos(heading);
    if(forward<5)return null;
    return {x:width/2+(dx*Math.cos(heading)-dy*Math.sin(heading))*focal/forward,y:horizon-(point.height_m-position.height_m)*focal/forward,depth:forward};
  }
  ctx.strokeStyle='#a9c4a22a';ctx.lineWidth=1;
  for(let d=100;d<=3000;d+=100){const y=horizon+(position.height_m+10)*focal/d;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();}
  for(let x=-8;x<=8;x++){ctx.beginPath();ctx.moveTo(width/2+x*15,horizon);ctx.lineTo(width/2+x*250,height);ctx.stroke();}
  // Visible lesson gates are conceptual airspace regions, never real-world objects.
  if(hints.zones) [...lesson.waypoints.entries()].reverse().forEach(([index,point])=>{
    const screen=project(point);if(!screen)return;
    const radius=Math.min(250,Math.max(7,point.radius_m*focal/screen.depth));
    if(screen.x+radius<0||screen.x-radius>width)return;
    const color=missionPointColor(index,progress.next);
    if(index===progress.next && point.type==='goal'){ctx.beginPath();ctx.arc(screen.x,screen.y,Math.max(3,radius*.2),0,Math.PI*2);ctx.fillStyle=MISSION_COLORS.goal;ctx.fill();}
    ctx.beginPath();ctx.arc(screen.x,screen.y,radius,0,Math.PI*2);ctx.fillStyle=color+'18';ctx.fill();ctx.strokeStyle=color;ctx.lineWidth=index===progress.next?4:2;ctx.stroke();ctx.fillStyle=color;ctx.font='13px sans-serif';ctx.fillText(`${index+1} · ${TYPE_LABELS[point.type]}`,screen.x+radius+8,screen.y);
  });
  $('guidance').hidden=!hints.arrows||progress.complete;
  if(!progress.complete){
    const goal=[...lesson.waypoints].reverse().find(p=>p.type==='goal')||lesson.waypoints.at(-1);
    for(const [prefix,point] of [['goal',goal],['next',lesson.waypoints[progress.next]]]){
      const angle=Math.atan2(point.x_m-position.x_m,point.y_m-position.y_m)-heading;
      $(prefix+'-arrow').style.transform=`rotate(${angle}rad)`;
      $(prefix+'-label').textContent=`${prefix==='goal'?'Финиш':'Следующая'} · ${Math.round(Math.hypot(point.x_m-position.x_m,point.y_m-position.y_m))} м`;
    }
  }
}
function frame(now) {
  const dt=Math.min(.05,(now-(previousTime??now))/1000);previousTime=now;
  advance(dt);drawMap();drawCamera();
  $('altitude').textContent=`${Math.round(position.height_m)} м`;
  $('speed').textContent=`${running?Math.round(lesson.demo_speed_m_s*3.6):0} км/ч`;
  requestAnimationFrame(frame);
}
try {
  const response=await fetch('/api/training-lessons');if(!response.ok)throw new Error('Миссии недоступны');
  ({lessons}=await response.json());
  if(!lessons.length||lessons.some(item=>item.coordinate_system!=='fictional_local'))throw new Error('Нужны миссии условного полигона');
  $('lesson').replaceChildren(...lessons.map(item=>new Option(item.name,item.id)));
  reset();requestAnimationFrame(frame);
} catch(error){$('progress').textContent=error.message;$('pause').disabled=true;$('restart').disabled=true;}

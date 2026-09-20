import {scannerContact, scaleContact, scannerGround} from './scanner-math.mjs';
import {missionPointColor, MISSION_COLORS} from './mission-colors.mjs';

export class MissionScanner {
  constructor(homeAltitude_m) {
    this.homeAltitude_m = homeAltitude_m;
    this.panel = document.getElementById('scanner-instrument');
    this.canvas = document.getElementById('scanner-canvas');
    this.range = document.getElementById('scanner-range');
    this.readout = document.getElementById('scanner-readout');
    this.lastFrame_ms = -Infinity;
  }
  update(pose, mission, next, completed) {
    if (this.panel.hidden || performance.now()-this.lastFrame_ms < 1000/30) return;
    this.lastFrame_ms = performance.now();
    const width = this.canvas.clientWidth, height = this.canvas.clientHeight;
    if (!width || !height) return;
    const dpr = window.devicePixelRatio || 1;
    if (this.canvas.width !== Math.round(width*dpr) || this.canvas.height !== Math.round(height*dpr)) {
      this.canvas.width = Math.round(width*dpr); this.canvas.height = Math.round(height*dpr);
    }
    const ctx = this.canvas.getContext('2d');
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
    const contacts = (mission?.waypoints || []).map((point,index)=>({point,index,...scannerContact(pose,point,this.homeAltitude_m)})).filter(contact=>Number.isFinite(contact.distance_m));
    const target = contacts.find(contact=>contact.index===next);
    const range_m = this.range.value === 'auto' ? Math.max(Number(this.range.dataset.minimumRangeM), target ? target.distance_m*1.2 : 0) : Number(this.range.value);
    const radius = Math.min(width/2-20,height/2-12), cx=width/2, cy=height/2;
    // Orthographic view of the aircraft's own horizontal plane, tilted toward
    // the viewer. Both stems and direct vectors use the same projection.
    const project = (x,y,z=0) => [cx+x*radius, cy-y*radius*.45-z*radius*.893];
    const line = (a,b,color,dashed=false) => {ctx.strokeStyle=color;ctx.setLineDash(dashed?[3,4]:[]);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();};
    ctx.lineWidth=1;
    ctx.fillStyle='#0b202be0';ctx.beginPath();ctx.arc(cx,cy,radius,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='#87cdd64d';ctx.stroke();
    const ground = scannerGround(pose,range_m);
    if (ground) {
      ctx.save();
      ctx.beginPath();ctx.arc(cx,cy,radius,0,Math.PI*2);ctx.clip();
      if (ground.rim.length) {
        ctx.beginPath();
        ground.rim.forEach((p,i) => i ? ctx.lineTo(...project(...p)) : ctx.moveTo(...project(...p)));
        ctx.closePath();ctx.fillStyle='#a9814940';ctx.fill();
        ctx.strokeStyle='#dfb87aad';ctx.stroke();
      }
      const foot=project(...ground.foot);
      line([cx,cy],foot,'#ffd28b',true);
      ctx.setLineDash([]);ctx.fillStyle='#ffd28b';
      ctx.beginPath();ctx.arc(...foot,3,0,Math.PI*2);ctx.fill();
      ctx.restore();
    }
    for (const fraction of [.5,1]) {ctx.beginPath();ctx.ellipse(cx,cy,radius*fraction,radius*.45*fraction,0,0,Math.PI*2);ctx.stroke();}
    line(project(-1,0),project(1,0),'#87cdd64d');line(project(0,-1),project(0,1),'#87cdd64d');
    ctx.fillStyle='#a6c6ce';ctx.font='10px sans-serif';ctx.textAlign='center';
    ctx.fillText('ВПЕРЁД',cx,cy-radius*.45-6);ctx.fillText(`${(range_m/1000).toFixed(2)} км`,cx,height-2);
    const drawContact = contact => {
      const {x,y,z,outside}=scaleContact(contact,range_m), p=project(x,y,z), foot=project(x,y);
      const color=missionPointColor(contact.index,next,completed), active=contact.index===next;
      ctx.lineWidth=active?2:1;
      line(foot,p,color+'b0');
      ctx.fillStyle=color+'80';ctx.beginPath();ctx.ellipse(...foot,3,1.5,0,0,Math.PI*2);ctx.fill();
      if(active) line([cx,cy],p,color+'a0',true);
      ctx.setLineDash([]);ctx.strokeStyle=color;ctx.fillStyle=color;
      ctx.beginPath();ctx.arc(...p,active?6:4,0,Math.PI*2);outside?ctx.stroke():ctx.fill();
      if(active && contact.point.type==='goal') {ctx.fillStyle=MISSION_COLORS.goal;ctx.beginPath();ctx.arc(...p,3,0,Math.PI*2);ctx.fill();}
      ctx.fillStyle=color;ctx.textAlign='left';ctx.fillText(`${contact.index+1}${outside?' ↗':''}`,p[0]+8,p[1]-4);
    };
    contacts.filter(c=>c.index!==next).sort((a,b)=>b.forward_m-a.forward_m).forEach(drawContact);
    if(target) drawContact(target);
    // Label each ring with its actual radius as the automatic range changes.
    ctx.font='10px sans-serif';ctx.textAlign='center';
    for (const fraction of [.5,1]) {
      const distance_m=range_m*fraction;
      const label=distance_m<1000 ? `R ${Math.round(distance_m)} м` : `R ${(distance_m/1000).toFixed(2)} км`;
      const [x,y]=project(0,-fraction);
      const labelWidth=ctx.measureText(label).width;
      ctx.fillStyle='#0b202bd9';ctx.fillRect(x-labelWidth/2-3,y-6,labelWidth+6,13);
      ctx.fillStyle='#bfdce2';ctx.fillText(label,x,y+4);
    }
    ctx.fillStyle='#f4f5ef';ctx.beginPath();ctx.moveTo(cx,cy-9);ctx.lineTo(cx+6,cy+7);ctx.lineTo(cx,cy+3);ctx.lineTo(cx-6,cy+7);ctx.closePath();ctx.fill();
    const missionText = target ? `Точка ${next+1} · ${(target.distance_m/1000).toFixed(2)} км · Δh ${target.height_difference_m>=0?'+':''}${Math.round(target.height_difference_m)} м` : mission ? 'Маршрут завершён' : 'Выберите миссию';
    const groundText = ground ? `Земля ↓ ${Math.round(ground.distance_m)} м AGL${ground.outside?' · вне масштаба':''}` : 'Земля: нет данных AGL';
    this.readout.textContent = `${groundText} · ${missionText}`;
  }
}

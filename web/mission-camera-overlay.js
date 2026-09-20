import {missionPointColor, MISSION_COLORS} from './mission-colors.mjs';
import {missionHeightM} from './mission-height.mjs';
const C=window.Cesium;

// Mission HUD is composited by the browser after Cesium's sensor effects.
export class MissionCameraOverlay {
  constructor(scene) {
    this.scene=scene;
    this.show=true;
    this.next=0;
    this.points=[];
    this.lineStart=new C.Cartesian3();
    this.lineEnd=new C.Cartesian3();
    this.lineRelative=new C.Cartesian3();
    this.screenStart=new C.Cartesian2();
    this.screenEnd=new C.Cartesian2();
    this.canvas=document.createElement('canvas');
    this.canvas.className='mission-camera-overlay';
    this.canvas.setAttribute('aria-label','Подсветка точек миссии');
    scene.main.container.append(this.canvas);
    scene.main.scene.postRender.addEventListener(()=>this.draw());
  }
  setMission(mission) {
    this.route=[];
    this.points=(mission?.waypoints || []).map(point=>{
      const height=missionHeightM(point,this.scene.physicalGroundM)+this.scene.geoidSeparationM;
      if(!Number.isFinite(height))return {point,center:null,rings:[]};
      const center=C.Cartesian3.fromDegrees(point.longitude_deg,point.latitude_deg,height);
      const frame=C.Transforms.eastNorthUpToFixedFrame(center);
      const rings=[0,1,2].map(axis=>Array.from({length:49},(_,index)=>{
        const angle=index/48*Math.PI*2, a=Math.cos(angle),b=Math.sin(angle);
        const offset=axis===0 ? new C.Cartesian3(point.radius_m*a,point.radius_m*b,0) : axis===1 ? new C.Cartesian3(point.radius_m*a,0,mission.height_tolerance_m*b) : new C.Cartesian3(0,point.radius_m*a,mission.height_tolerance_m*b);
        return C.Matrix4.multiplyByPoint(frame,offset,new C.Cartesian3());
      }));
      return {point,center,rings};
    });
    for(let index=1;index<this.points.length;index++) {
      if(!this.points[index-1].center || !this.points[index].center)continue;
      const a=C.Cartographic.fromCartesian(this.points[index-1].center),b=C.Cartographic.fromCartesian(this.points[index].center);
      const geodesic=new C.EllipsoidGeodesic(a,b);
      if(geodesic.surfaceDistance<1e-6) {
        this.route.push({start:this.points[index-1].center,end:this.points[index].center,index});
        continue;
      }
      const count=Math.max(1,Math.ceil(geodesic.surfaceDistance/mission.route_render_step_m));
      let previous=this.points[index-1].center;
      for(let step=1;step<=count;step++) {
        const fraction=step/count;
        const location=geodesic.interpolateUsingFraction(fraction);
        const next=C.Cartesian3.fromRadians(location.longitude,location.latitude,a.height+(b.height-a.height)*fraction);
        this.route.push({start:previous,end:next,index});previous=next;
      }
    }
  }
  draw() {
    const debug=this.scene.view==='orbit';
    this.canvas.hidden=!this.show && !debug;
    if(this.canvas.hidden)return;
    const scene=this.scene.main.scene, width=scene.canvas.clientWidth,height=scene.canvas.clientHeight,dpr=window.devicePixelRatio||1;
    if(this.canvas.width!==Math.round(width*dpr)||this.canvas.height!==Math.round(height*dpr)){
      this.canvas.width=Math.round(width*dpr);this.canvas.height=Math.round(height*dpr);
    }
    const ctx=this.canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
    const camera=scene.camera;
    if(debug) this.drawRoute(ctx,scene,camera);
    if(!this.show && !debug)return;
    const project=position=>{
      const relative=C.Cartesian3.subtract(position,camera.positionWC,new C.Cartesian3());
      if(C.Cartesian3.dot(relative,camera.directionWC)<=camera.frustum.near)return null;
      return C.SceneTransforms.worldToWindowCoordinates(scene,position);
    };
    const ordered=this.points.map((entry,index)=>({...entry,index})).filter(entry=>entry.center).map(entry=>({...entry,distance:C.Cartesian3.distanceSquared(entry.center,camera.positionWC)})).sort((a,b)=>b.distance-a.distance);
    for(const {point,center,rings,index} of ordered){
      const screen=project(center);if(!screen)continue;
      const completed=this.completed ? this.completed.has(index) : index<this.next,color=missionPointColor(index,this.next,this.completed);
      ctx.globalAlpha=1;ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=index===this.next?2:1;
      if(completed){ctx.beginPath();ctx.arc(screen.x,screen.y,1.5,0,Math.PI*2);ctx.fill();}
      else {
        for(const ring of rings){
          ctx.beginPath();let connected=false, clipped=false;
          for(const position of ring){const p=project(position);if(!p){connected=false;clipped=true;continue;}if(connected)ctx.lineTo(p.x,p.y);else ctx.moveTo(p.x,p.y);connected=true;}
          if(!clipped){ctx.globalAlpha=.05;ctx.fill();ctx.globalAlpha=1;}
          ctx.stroke();
        }
        if(index===this.next && point.type==='goal'){
          ctx.fillStyle=MISSION_COLORS.goal;ctx.beginPath();ctx.arc(screen.x,screen.y,5,0,Math.PI*2);ctx.fill();
        }
      }
      ctx.font='13px sans-serif';ctx.textAlign='left';
      const distance_m=C.Cartesian3.distance(center,this.scene.position);
      const distanceLabel=distance_m<1000 ? `${Math.round(distance_m)} м` : `${(distance_m/1000).toFixed(2)} км`;
      const label=`${index+1} · ${point.name || 'Точка'} · до точки ${distanceLabel}`;
      ctx.globalAlpha=completed?.08:.65;ctx.fillStyle='#000';ctx.fillRect(screen.x+6,screen.y-17,ctx.measureText(label).width+8,20);
      ctx.globalAlpha=completed?.25:1;ctx.fillStyle=color;ctx.fillText(label,screen.x+10,screen.y-3);
    }
    ctx.globalAlpha=1;
  }
  drawRoute(ctx,scene,camera) {
    // Clip each segment at the camera near plane, including when one waypoint is behind us.
    const started=performance.now(), near=camera.frustum.near+0.01;
    ctx.globalAlpha=1;ctx.lineWidth=2;
    for(const {start:worldStart,end:worldEnd,index} of this.route || []) {
      C.Cartesian3.clone(worldStart,this.lineStart);
      C.Cartesian3.clone(worldEnd,this.lineEnd);
      const a=C.Cartesian3.dot(C.Cartesian3.subtract(this.lineStart,camera.positionWC,this.lineRelative),camera.directionWC);
      const b=C.Cartesian3.dot(C.Cartesian3.subtract(this.lineEnd,camera.positionWC,this.lineRelative),camera.directionWC);
      if(a<=near && b<=near)continue;
      if(a<near)C.Cartesian3.lerp(this.lineStart,this.lineEnd,(near-a)/(b-a),this.lineStart);
      else if(b<near)C.Cartesian3.lerp(this.lineStart,this.lineEnd,(near-a)/(b-a),this.lineEnd);
      const start=C.SceneTransforms.worldToWindowCoordinates(scene,this.lineStart,this.screenStart);
      const end=C.SceneTransforms.worldToWindowCoordinates(scene,this.lineEnd,this.screenEnd);
      if(!start || !end)continue;
      ctx.beginPath();ctx.moveTo(start.x,start.y);ctx.lineTo(end.x,end.y);
      // A dark casing separates the mission from the terrain debug grid below the HUD.
      ctx.strokeStyle='#10262d';ctx.lineWidth=5;ctx.stroke();
      ctx.strokeStyle=missionPointColor(index,this.next,this.completed);ctx.lineWidth=2;ctx.stroke();
    }
    this.routeDrawMs=performance.now()-started;
  }
}

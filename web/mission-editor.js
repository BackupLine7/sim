import {addMissionLegLabel} from './mission-leg-label.js';
const C = window.Cesium;
export class MissionEditor {
  constructor(missions) {
    this.missions=missions;this.scene=missions.scene;this.index=-1;
    this.layer=new C.CustomDataSource('Mission draft');this.scene.map.dataSources.add(this.layer);
    this.ui=Object.fromEntries(['name','point','fields','point-name','type','altitude','radius','delete','save','cancel','message','up','down'].map(k=>[k,document.getElementById('editor-'+k)]));
    this.ui.up.onclick=()=>this.reorder(-1);
    this.ui.down.onclick=()=>this.reorder(1);
    document.getElementById('mission-new').onclick=()=>this.begin();
    document.getElementById('mission-edit').onclick=()=>this.begin(missions.selected);
    this.ui.cancel.onclick=()=>this.end();this.ui.save.onclick=()=>this.save();
    this.ui.point.onchange=()=>{this.index=Number(this.ui.point.value);this.render();};
    for (const key of ['point-name','type','altitude','radius']) this.ui[key].onchange=()=>this.editPoint();
    this.ui.delete.onclick=()=>{this.draft.waypoints.splice(this.index,1);this.index=Math.min(this.index,this.draft.waypoints.length-1);this.render();};
    const canvas=this.scene.map.canvas;
    canvas.addEventListener('pointerdown',e=>this.down(e),true);
    canvas.addEventListener('pointermove',e=>this.move(e),true);
    canvas.addEventListener('pointerup',e=>this.up(e),true);
    canvas.addEventListener('pointercancel',()=>this.release());
    window.addEventListener('blur',()=>this.release());
    window.addEventListener('beforeunload',event=>{if(this.draft){event.preventDefault();event.returnValue='';}});
  }
  begin(mission) {
    if (!this.missions.defaults) {this.missions.message.textContent="Дождитесь загрузки списка миссий";return;}
    this.previousFollow=this.scene.followMap;this.scene.followMap=false;
    this.id=mission && !mission.id.startsWith('training-') ? mission.id : null;
    this.draft=mission ? structuredClone(mission) : {name:'Новая миссия',height_tolerance_m:this.missions.defaults.height_tolerance_m,waypoints:[]};
    this.draft.waypoints=this.draft.waypoints.map(p=>({...p,type:['transit','goal','land'].includes(p.type)?p.type:'transit'}));
    this.index=this.draft.waypoints.length?0:-1;
    this.ui.name.value=this.draft.name;
    this.ui.message.textContent=mission?.id.startsWith('training-')?'Учебный маршрут будет сохранён отдельной миссией.':'Изменения применятся при следующем запуске маршрута.';
    document.getElementById('mission-editor').hidden=false;
    for(const id of ['mission-new','mission-edit','mission-reload','mission-fit','center']) document.getElementById(id).disabled=true;
    this.missions.select.disabled=false;
    this.missions.layer.show=false;
    this.missions.updateStatus(this.missions.status);
    if(mission)this.missions.fit();
    this.render();
  }
  end(showSelection=true) {
    this.draft=null;this.index=-1;
    document.getElementById('mission-editor').hidden=true;this.scene.followMap=this.previousFollow;
    for(const id of ['mission-new','mission-edit','mission-reload','map-mission','mission-fit','center']) document.getElementById(id).disabled=false;
    this.release();this.layer.entities.removeAll();this.missions.layer.show=true;
    if(showSelection)this.missions.show(this.missions.select.value);
  }
  editPoint() {
    if(this.index<0)return;
    if(this.ui.type.value==='goal'){this.ui.altitude.value=0;this.ui.altitude.disabled=true;}
    else if(this.ui.altitude.disabled){this.ui.altitude.disabled=false;this.ui.altitude.value=this.scene.settings.airfield.takeoff_altitude_m;}
    if(!this.ui.altitude.reportValidity() || !this.ui.radius.reportValidity())return;
    Object.assign(this.draft.waypoints[this.index],{name:this.ui['point-name'].value,type:this.ui.type.value,altitude_relative_m:this.ui.altitude.valueAsNumber,radius_m:this.ui.radius.valueAsNumber});
    this.render();
  }
  reorder(offset) {
    const next=this.index+offset;
    if(!this.draft || this.index<0 || next<0 || next>=this.draft.waypoints.length)return;
    this.editPoint();
    const [point]=this.draft.waypoints.splice(this.index,1);
    this.draft.waypoints.splice(next,0,point);this.index=next;this.render();
  }
  render() {
    this.layer.entities.removeAll();
    this.ui.point.replaceChildren(...this.draft.waypoints.map((p,i)=>new Option(`${i+1}. ${p.name || 'Точка'}`,i)));
    this.ui.point.value=String(this.index);this.ui.fields.hidden=this.index<0;
    const selected=this.draft.waypoints[this.index];
    if(selected){this.ui['point-name'].value=selected.name||'';this.ui.type.value=selected.type;this.ui.altitude.disabled=selected.type==='goal';this.ui.altitude.value=selected.type==='goal'?0:selected.altitude_relative_m;this.ui.altitude.title=selected.type==='goal'?'Цель находится на поверхности ландшафта (0 м AGL)':'';this.ui.radius.value=selected.radius_m;}
    this.ui.up.disabled=this.index<=0;
    this.ui.down.disabled=this.index<0 || this.index>=this.draft.waypoints.length-1;
    this.ui.save.disabled=this.draft.waypoints.length<2;
    const positions=this.draft.waypoints.map(p=>C.Cartesian3.fromDegrees(p.longitude_deg,p.latitude_deg,this.scene.settings.ground_m+3));
    if(positions.length>1)this.layer.entities.add({polyline:{positions,width:3,material:C.Color.YELLOW}});
    for(let i=1;i<positions.length;i++)addMissionLegLabel(this.layer.entities,positions[i-1],positions[i]);
    positions.forEach((position,i)=>this.layer.entities.add({id:'draft-'+i,position,
      point:{pixelSize:i===this.index?16:11,color:i===this.index?C.Color.LIME:C.Color.YELLOW,outlineColor:C.Color.BLACK,outlineWidth:2,disableDepthTestDistance:Infinity},
      label:{text:`${i+1} · ${{transit:'Пролёт',goal:'Цель',land:'Посадка'}[this.draft.waypoints[i].type]}`,font:'13px sans-serif',pixelOffset:new C.Cartesian2(14,-18),showBackground:true,disableDepthTestDistance:Infinity}}));
  }
  screen(e){const r=this.scene.map.canvas.getBoundingClientRect();return new C.Cartesian2(e.clientX-r.left,e.clientY-r.top);}
  location(e){const g=this.scene.settings.ground_m,r=C.Ellipsoid.WGS84.radii;
    const p=this.scene.map.camera.pickEllipsoid(this.screen(e),new C.Ellipsoid(r.x+g,r.y+g,r.z+g));
    if(!p)return null;const c=C.Cartographic.fromCartesian(p);return {longitude_deg:C.Math.toDegrees(c.longitude),latitude_deg:C.Math.toDegrees(c.latitude)};}
  down(e){
    if(!this.draft || e.button!==0)return;
    const hit=this.scene.map.scene.pick(this.screen(e))?.id;
    this.pointer={x:e.clientX,y:e.clientY,id:e.pointerId,drag:!!hit && this.layer.entities.contains(hit) && /^draft-\d+$/.test(hit.id)};
    if(this.pointer.drag){this.index=Number(hit.id.slice(6));this.render();this.controllerEnabled=this.scene.map.scene.screenSpaceCameraController.enableInputs;this.scene.map.scene.screenSpaceCameraController.enableInputs=false;this.scene.map.canvas.setPointerCapture(e.pointerId);e.stopImmediatePropagation();e.preventDefault();}
  }
  move(e){if(!this.pointer?.drag)return;const p=this.location(e);if(p){Object.assign(this.draft.waypoints[this.index],p);this.render();}e.stopImmediatePropagation();}
  up(e){
    if(!this.pointer)return;const pointer=this.pointer;
    if(pointer.drag){e.stopImmediatePropagation();e.preventDefault();}
    else if(Math.hypot(e.clientX-pointer.x,e.clientY-pointer.y)<5){const p=this.location(e);if(p){this.draft.waypoints.push({...p,name:`Точка ${this.draft.waypoints.length+1}`,type:'transit',altitude_relative_m:this.scene.settings.airfield.takeoff_altitude_m,radius_m:this.missions.defaults.radius_m});this.index=this.draft.waypoints.length-1;this.render();}}
    this.release();
  }
  release(){if(this.pointer?.drag){this.scene.map.scene.screenSpaceCameraController.enableInputs=this.controllerEnabled;const c=this.scene.map.canvas;if(c.hasPointerCapture(this.pointer.id))c.releasePointerCapture(this.pointer.id);}this.pointer=null;}
  async save(){
    if(!this.draft || this.saving)return;
    if(!this.ui.name.reportValidity())return;
    if(this.index>=0 && (!this.ui.altitude.reportValidity() || !this.ui.radius.reportValidity()))return;
    this.editPoint();this.draft.name=this.ui.name.value.trim();this.saving=true;this.ui.save.disabled=true;this.ui.cancel.disabled=true;this.missions.select.disabled=true;
    try{const response=await fetch('/api/missions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:this.id,mission:this.draft})});const result=await response.json();if(!response.ok)throw new Error(result.error);
      this.end(false);
      this.missions.restoreSelection=false;
      const saved={...result,route_render_step_m:this.missions.defaults.route_render_step_m};
      const existing=this.missions.missions.findIndex(m=>m.id===saved.id);
      if(existing<0){this.missions.missions.push(saved);this.missions.select.add(new Option(saved.name,saved.id));}
      else {this.missions.missions[existing]=saved;const option=[...this.missions.select.options].find(option=>option.value===saved.id);if(option)option.text=saved.name;}
      this.missions.select.value=saved.id;this.missions.show(saved.id);
    }catch(error){this.ui.message.textContent=error.message;}
    finally{this.saving=false;this.ui.save.disabled=false;this.ui.cancel.disabled=false;this.missions.select.disabled=false;}
  }
}

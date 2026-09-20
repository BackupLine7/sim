import {MissionEditor} from './mission-editor.js';
import {addMissionLegLabel} from './mission-leg-label.js';
import {MissionCameraOverlay} from './mission-camera-overlay.js';
import {MissionScanner} from './mission-scanner.js';
import {missionPointColor, MISSION_COLORS} from './mission-colors.mjs';
const C = window.Cesium;

export class MissionMap {
  constructor(scene) {
    this.scene = scene;
    this.layer = new C.CustomDataSource('Selected mission');
    scene.map.dataSources.add(this.layer);
    this.cameraOverlay = new MissionCameraOverlay(scene);
    this.scanner = new MissionScanner(scene.physicalGroundM);
    this.followButton = document.getElementById('mission-follow');
    this.completedByMission = new Map();
    try{for(const [id,indices] of Object.entries(JSON.parse(localStorage.getItem('flightlab-mission-completed') || '{}')))if(Array.isArray(indices))this.completedByMission.set(id,new Set(indices));}catch{}
    this.checklist = document.getElementById('mission-checklist');
    this.followButton.onclick = () => this.onCommand?.('mission', {mission_id:this.selected.id, completed:[...this.completed()]});
    this.hints = {zones:true};
    try {Object.assign(this.hints, JSON.parse(localStorage.getItem('flightlab-mission-hints') || '{}'));} catch {}
    for (const key of ['zones']) {
      const input = document.getElementById('mission-' + key);
      input.checked = this.hints[key];
      input.onchange = () => {
        this.hints[key] = input.checked;
        try {localStorage.setItem('flightlab-mission-hints', JSON.stringify(this.hints));} catch {}
        this.cameraOverlay.show = this.hints.zones;
      };
    }
    this.cameraOverlay.show = this.hints.zones;
    this.status = {};
    this.restoreSelection = true;
    this.savedSelection = "";
    try {this.savedSelection = localStorage.getItem("flightlab-selected-mission") || "";} catch {}
    this.select = document.getElementById('map-mission');
    this.message = document.getElementById('mission-status');
    this.fitButton = document.getElementById('mission-fit');
    this.select.onchange = () => this.changeSelection();
    this.fitButton.onclick = () => this.fit();
    document.getElementById('mission-reload').onclick = () => this.load();
    document.getElementById('mission-delete').onclick=async()=>{
      if(this.editor?.draft){this.message.textContent='Сначала сохраните или отмените редактирование миссии.';return;}
      const mission=this.selected;if(!mission){this.message.textContent='Выберите миссию для удаления.';return;}
      try {
        const response=await fetch('/api/missions',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:mission.id})});
        const result=await response.json();if(!response.ok)throw Error(result.error);
        this.completedByMission.delete(mission.id);this.restoreSelection=false;this.savedSelection='';
        this.select.value='';await this.load();
        this.message.textContent=`Миссия «${mission.name}» удалена из списка.`;
      }catch(error){this.message.textContent=error.message;}
    };
    this.missions = [];
    this.editor = new MissionEditor(this);
  }
  async load() {
    const previous = this.select.value || (this.restoreSelection ? this.savedSelection : "");
    try {
      const response = await fetch('/api/missions', {cache: 'no-store'});
      if (!response.ok) throw new Error('Не удалось прочитать миссии');
      const catalog = await response.json();
      this.missions = catalog.missions;
      this.defaults = catalog.defaults;
      this.select.replaceChildren(new Option('Без миссии', ''));
      for (const mission of this.missions)
        this.select.add(new Option(mission.name, mission.id));
      this.select.value = this.missions.some(m => m.id === previous) ? previous : '';
      this.show(this.select.value);
      if (catalog.errors.length) this.message.textContent = catalog.errors.join('; ');
    } catch (error) {
      this.message.textContent = error.message;
    }
  }
  show(id) {
    if (this.restoreSelection && this.status.mission_id && this.missions.some(m => m.id === this.status.mission_id)) {
      id = this.status.mission_id;
      this.restoreSelection = false;
      this.select.value = id;
    }
    this.layer.entities.removeAll();
    this.selected = this.missions.find(m => m.id === id);
    document.getElementById('mission-delete').textContent=this.selected ? 'Удалить «'+this.selected.name+'»' : 'Удалить выбранную миссию';
    document.getElementById('mission-delete').disabled=!this.selected;
    this.checklist.replaceChildren();
    this.checkboxes = (this.selected?.waypoints || []).map((point,index) => {
      const label = document.createElement('label'), input = document.createElement('input'), text = document.createElement('span');
      input.type='checkbox';
      text.textContent=`${index+1}. ${point.name || ({transit:'Пролёт',goal:'Цель',land:'Посадка'}[point.type] ?? 'Точка')}`;
      label.append(input,text);this.checklist.append(label);
      input.onchange=()=>{
        if(input.checked)this.completed().add(index);else this.completed().delete(index);
        this.persistCompleted();
        if(this.status.mission_active && this.status.mission_id===this.selected.id)
          this.onCommand?.('mission_check',{mission_id:this.selected.id,index,checked:input.checked});
        this.updateStatus(this.status,true);
      };
      return input;
    });
    if (this.selected || !this.restoreSelection) {
      try {localStorage.setItem("flightlab-selected-mission", this.selected?.id || "");} catch {}
    }
    this.cameraOverlay.setMission(this.selected);
    this.resolveGoalHeights(this.selected);
    this.fitButton.disabled = !this.selected;
    document.getElementById('mission-edit').disabled = !this.selected;
    this.updateStatus(this.status);
    if (!this.selected) return;
    const positions = this.selected.waypoints.map(point => C.Cartesian3.fromDegrees(
      point.longitude_deg, point.latitude_deg, this.scene.settings.ground_m + 2));
    for(let i=1;i<positions.length;i++)addMissionLegLabel(this.layer.entities,positions[i-1],positions[i]);
    this.selected.waypoints.forEach((point, index) => {
      const color = () => C.Color.fromCssColorString(missionPointColor(index, this.next,this.completed()));
      const material=new C.PolylineDashMaterialProperty({color:new C.CallbackProperty(color, false), dashPattern:new C.CallbackProperty(() => index < this.next ? 65535 : 255, false)});
      if (index) this.layer.entities.add({polyline: {
        positions:[positions[index-1], positions[index]], width:3,
        material, depthFailMaterial:material,
      }});
    });
    const markers = new Map();
    this.selected.waypoints.forEach((point, index) => {
      const key = `${point.latitude_deg},${point.longitude_deg}`;
      if (markers.has(key)) markers.get(key).numbers.push(index + 1);
      else markers.set(key, {position: positions[index], numbers: [index + 1]});
    });
    for (const {position, numbers} of markers.values()) {
      const markerIndex = () => numbers.includes(this.next+1) ? this.next : (numbers.find(n => n > this.next) ?? numbers.at(-1))-1;
      const color = () => C.Color.fromCssColorString(missionPointColor(markerIndex(), this.next,this.completed()));
      const activeGoal = () => numbers.includes(this.next+1) && this.selected.waypoints[this.next]?.type === 'goal';
      this.layer.entities.add({
      position,
      point: {pixelSize: 10, color: new C.CallbackProperty(() => activeGoal() ? C.Color.fromCssColorString(MISSION_COLORS.goal) : color(), false), outlineColor: new C.CallbackProperty(() => activeGoal() ? color() : C.Color.BLACK, false), outlineWidth: new C.CallbackProperty(() => activeGoal() ? 4 : 2, false), disableDepthTestDistance: Number.POSITIVE_INFINITY},
      label: {text: numbers.join(' / '), font: 'bold 13px sans-serif',
        pixelOffset: new C.Cartesian2(12, -14), fillColor: new C.CallbackProperty(color, false),
        showBackground: true, disableDepthTestDistance: Number.POSITIVE_INFINITY},
    });
    }
    this.bounds = C.BoundingSphere.fromPoints(positions);
  }
  completed() {
    const id=this.selected?.id;
    if(!this.completedByMission.has(id))this.completedByMission.set(id,new Set());
    return this.completedByMission.get(id);
  }
  persistCompleted() {
    try{localStorage.setItem('flightlab-mission-completed',JSON.stringify(Object.fromEntries([...this.completedByMission].map(([id,set])=>[id,[...set]]))));}catch{}
  }
  changeSelection() {
    const id=this.select.value;
    if(this.editor?.draft) {
      if(!window.confirm('Отменить несохранённые изменения миссии и переключиться на другую?')) {
        this.select.value=this.selected?.id || '';
        return;
      }
      this.restoreSelection=false;
      this.editor.end();
    }
    this.restoreSelection=false;this.show(id);
  }
  async resolveGoalHeights(mission) {
    this.heightRequest?.abort();clearTimeout(this.heightRetry);
    const request=this.heightRequest=new AbortController();
    if(!mission)return;
    try {
      let pending=false;
      for(const point of mission.waypoints.filter(point=>point.type==='goal')) {
        const response=await fetch(`/api/start-elevation?lat=${point.latitude_deg}&lon=${point.longitude_deg}`,{signal:request.signal});
        if(!response.ok)throw Error('Не удалось получить высоту цели');
        const result=await response.json();
        if(result.ready && Number.isFinite(result.elevation_asl_m))point.terrain_elevation_asl_m=result.elevation_asl_m;
        else pending=true;
      }
      if(request.signal.aborted || this.selected!==mission)return;
      this.cameraOverlay.setMission(mission);
      if(pending)this.heightRetry=setTimeout(()=>this.resolveGoalHeights(mission),1000);
    }catch(error){if(error.name!=='AbortError')this.message.textContent='Высота цели недоступна. Требуется работающий источник рельефа.';}
  }
  updateStatus(status,localEdit=false) {
    this.status = status;
    if (this.restoreSelection && !this.editor?.draft && status.mission_id && this.missions.some(m => m.id === status.mission_id)) {
      this.restoreSelection = false;
      this.select.value = status.mission_id;
      this.show(status.mission_id);
      return;
    }
    const matches = this.selected && status.mission_id === this.selected.id;
    const progressKey=matches ? JSON.stringify([status.mission_id,status.mission_completed || []]) : null;
    if(!localEdit && matches && (status.mission_active || (status.mission_complete && !this.statusWasComplete)) && this.lastProgressKey!==progressKey) {
      this.completedByMission.set(this.selected.id,new Set(status.mission_completed || []));
      this.lastProgressKey=progressKey;
      this.persistCompleted();
    }
    this.statusWasComplete=!!status.mission_complete;
    this.next = this.selected ? this.selected.waypoints.findIndex((_,i)=>!this.completed().has(i)) : 0;
    if(this.next<0)this.next=this.selected.waypoints.length;
    this.checkboxes?.forEach((input,index)=>{
      input.checked=this.completed().has(index);
      input.disabled=!!this.editor?.draft || (!!status.mission_active && !status.connected);
      input.parentElement.classList.toggle('current',!!matches && !!status.mission_active && index===this.next);
    });
    this.cameraOverlay.next = this.next;
    this.cameraOverlay.completed=this.completed();
    this.scene.map.scene.requestRender();
    this.scene.main.scene.requestRender();
    if(matches && status.mission_active && status.mission_waypoints) {
      const heights=JSON.stringify(status.mission_waypoints);
      if(this.effectiveHeights!==heights){
        this.effectiveHeights=heights;
        this.flightMission={...this.selected,waypoints:status.mission_waypoints};
        this.cameraOverlay.setMission(this.flightMission);
      }
    }else {this.flightMission=null;this.effectiveHeights=null;}
    const ready = status.connected && status.physics_live && !status.restarting;
    const completion = status.mission_end === 'goal' ? 'Цель достигнута' : status.mission_end === 'land' ? 'Маршрут пройден · посадка' : 'Завершено · ожидание на круге';
    this.followButton.disabled = !!this.editor?.draft || !this.selected || !ready || status.phase !== 'flight' || (matches && status.mission_active);
    this.message.textContent = this.selected ? `${this.completed().size} / ${this.selected.waypoints.length} точек · ${matches && status.mission_complete ? completion : matches && status.mission_active ? 'Автопилот следует маршруту' : status.phase === 'flight' ? 'Нажмите «Следовать» для старта маршрута' : 'Следование доступно после взлёта'}` : '';
    if(this.selected && this.next===this.selected.waypoints.length){this.message.textContent=`${this.completed().size} / ${this.selected.waypoints.length} · Все точки отмечены пройденными`;this.followButton.disabled=true;}
  }
  update(pose) {
    this.scanner.update(pose, this.flightMission || this.selected, this.next,this.completed());
  }
  fit() {
    if (!this.selected) return;
    this.scene.followMap = false;
    this.scene.map.camera.viewBoundingSphere(this.bounds, new C.HeadingPitchRange(
      this.scene.navigation?.heading ?? 0, -Math.PI / 2, Math.max(400, this.bounds.radius * 3)));
    this.scene.map.camera.lookAtTransform(C.Matrix4.IDENTITY);
  }
}

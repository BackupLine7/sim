const C=window.Cesium;
export class StartLocationsPanel {
  constructor(scene, missions, command) {
    this.scene=scene;this.missions=missions;this.command=command;
    this.select=document.getElementById('start-location');
    this.settingsSelect=document.getElementById('settings-start-location');
    this.settingsSelect.onchange=()=>{this.select.value=this.settingsSelect.value;this.showSelected(true);};
    this.marker=scene.map.entities.add({show:false,position:scene.position,
      point:{pixelSize:12,color:C.Color.LIME,outlineColor:C.Color.BLACK,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},
      label:{text:'СТАРТ',font:'bold 12px sans-serif',pixelOffset:new C.Cartesian2(12,-18),showBackground:true,disableDepthTestDistance:Number.POSITIVE_INFINITY}});
    this.select.onchange=()=>this.showSelected(true);
    this.message=document.getElementById('start-message');
    this.form=document.getElementById('start-form');
    this.heightRequest=null;
    for(const name of ['latitude_deg','longitude_deg','elevation_asl_m'])this.form.elements[name].addEventListener('input',()=>this.cancelHeightRequest());
    this.apply=document.getElementById('start-apply');
    this.apply.onclick=()=>{
      if(missions.editor?.draft){this.message.textContent='Сначала сохраните или отмените редактирование миссии.';return;}
      this.command('restart',{start_id:this.select.value});
    };
    document.getElementById('start-new').onclick=()=>{
      if(missions.editor?.draft){this.message.textContent='Сначала завершите редактирование миссии.';return;}
      this.cancelHeightRequest();this.form.reset();
      this.editingId=null;
      this.form.hidden=false;
      this.pointer=null;
      this.form.elements.heading_deg.value=scene.settings.heading_deg;
      document.getElementById('start-pick').click();
    };
    document.getElementById('start-edit').onclick=()=>{
      if(missions.editor?.draft){this.message.textContent='Сначала завершите редактирование миссии.';return;}
      const point=this.locations?.find(p=>p.id===this.select.value);if(!point || point.id==='default')return;
      this.cancelHeightRequest();this.form.reset();this.editingId=point.id;this.picking=false;this.pointer=null;
      for(const key of ['name','latitude_deg','longitude_deg','elevation_asl_m','heading_deg'])this.form.elements[key].value=point[key];
      this.form.hidden=false;this.message.textContent='Редактирование «'+point.name+'». Изменения вступят в силу при следующем старте здесь.';
    };
    document.getElementById('start-cancel').onclick=()=>{this.cancelHeightRequest();this.form.hidden=true;this.editingId=null;this.picking=false;this.message.textContent='';};
    document.getElementById('start-pick').onclick=()=>{this.cancelHeightRequest();this.picking=true;scene.followMap=false;this.message.textContent='Щёлкните на карте — высота площадки будет взята из рельефа.';window.dispatchEvent(new CustomEvent('settings-map-edit',{detail:'starts'}));};
    window.addEventListener('settings-editor-return',()=>{this.picking=false;});
    const canvas=scene.map.canvas;
    canvas.addEventListener('pointerdown',event=>{if(this.picking)this.pointer=[event.clientX,event.clientY];});
    canvas.addEventListener('pointerup',event=>{
      if(!this.picking || !this.pointer || Math.hypot(event.clientX-this.pointer[0],event.clientY-this.pointer[1])>5)return;
      const r=canvas.getBoundingClientRect(),position=scene.map.camera.pickEllipsoid(new C.Cartesian2(event.clientX-r.left,event.clientY-r.top));
      if(!position)return;
      const point=C.Cartographic.fromCartesian(position);
      this.form.elements.latitude_deg.value=C.Math.toDegrees(point.latitude).toFixed(6);
      this.form.elements.longitude_deg.value=C.Math.toDegrees(point.longitude).toFixed(6);
      this.pointer=null;
      this.picking=false;
      this.loadHeight();
      document.getElementById('return-editor-settings').click();
    });
    this.form.onsubmit=async event=>{
      event.preventDefault();
      if(!this.form.reportValidity())return;
      const data=Object.fromEntries(new FormData(this.form));
      if(this.editingId)data.id=this.editingId;
      if(['latitude_deg','longitude_deg','elevation_asl_m','heading_deg'].some(key=>!String(data[key]??'').trim())){
        this.message.textContent='Выберите место на карте или введите координаты, высоту и курс.';return;
      }
      for(const key of ['latitude_deg','longitude_deg','elevation_asl_m','heading_deg'])data[key]=Number(data[key]);
      try {
        const response=await fetch('/api/starts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
        const result=await response.json();if(!response.ok)throw Error(result.error);
        await this.load(result.id);this.form.hidden=true;this.picking=false;this.editingId=null;
        this.message.textContent='Сохранено. Чтобы перенести самолёт, нажмите «Начать здесь».';
      }catch(error){this.message.textContent=error.message;}
    };
    document.getElementById('start-delete').onclick=async()=>{
      const point=this.locations?.find(p=>p.id===this.select.value);if(!point)return;
      if(point.id==='default'){this.message.textContent='Исходную площадку удалить нельзя.';return;}
      try {
        const response=await fetch('/api/starts',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:point.id})});
        const result=await response.json();if(!response.ok)throw Error(result.error);
        await this.load();this.message.textContent=`Площадка «${point.name}» удалена из списка. Текущий полёт не изменён.`;
      }catch(error){this.message.textContent=error.message;}
    };
    this.load();
  }
  cancelHeightRequest() {
    this.heightRequest?.abort();this.heightRequest=null;
    this.form.querySelector('[type=submit]').disabled=false;
  }
  async loadHeight() {
    this.cancelHeightRequest();
    const request=new AbortController();this.heightRequest=request;
    const latitude=this.form.elements.latitude_deg.value,longitude=this.form.elements.longitude_deg.value;
    this.form.elements.elevation_asl_m.value='';
    this.form.querySelector('[type=submit]').disabled=true;
    this.message.textContent='Определяется высота ландшафта…';
    try {
      while(!request.signal.aborted) {
        const response=await fetch(`/api/start-elevation?lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}`,{signal:request.signal});
        const data=await response.json();if(!response.ok)throw Error(data.error||'Не удалось определить высоту');
        if(request.signal.aborted)return;
        if(data.ready) {
          this.form.elements.elevation_asl_m.value=Number(data.elevation_asl_m).toFixed(2);
          this.message.textContent=`Высота по рельефу: ${this.form.elements.elevation_asl_m.value} м над уровнем моря. Укажите название и курс, затем сохраните.`;
          return;
        }
        this.message.textContent='Загружаются высоты для выбранного места…';
        await new Promise(resolve=>setTimeout(resolve,1000));
      }
    } catch(error) {
      if(!request.signal.aborted)this.message.textContent=error.message+' Высоту можно указать вручную.';
    } finally {
      if(this.heightRequest===request)this.cancelHeightRequest();
    }
  }
  async load(selected) {
    try {
      const response=await fetch('/api/starts');if(!response.ok)throw Error('Список стартов недоступен');
      const data=await response.json();this.locations=data.locations;this.select.replaceChildren(...data.locations.map(point=>new Option(point.name,point.id)));
      this.settingsSelect.replaceChildren(...data.locations.map(point=>new Option(point.name,point.id)));
      this.select.value=data.locations.some(p=>p.id===(selected||data.active_id)) ? (selected||data.active_id) : 'default';
      this.showSelected(false);
    }catch(error){this.message.textContent=error.message;}
  }
  showSelected(center) {
    const point=this.locations?.find(point=>point.id===this.select.value);if(!point)return;
    this.settingsSelect.value=point.id;
    document.getElementById('settings-start-details').textContent=`${point.latitude_deg.toFixed(6)}°, ${point.longitude_deg.toFixed(6)}° · ${point.elevation_asl_m} м · курс ${point.heading_deg}°`;
    document.getElementById('start-delete').textContent='Удалить «'+point.name+'»';
    document.getElementById('start-delete').disabled=point.id==='default';
    document.getElementById('start-edit').disabled=point.id==='default';
    this.marker.position=C.Cartesian3.fromDegrees(point.longitude_deg,point.latitude_deg,point.elevation_asl_m+this.scene.geoidSeparationM);
    this.marker.show=true;this.marker.label.text='СТАРТ · '+point.name;
    if(center){this.scene.followMap=false;this.scene.map.camera.setView({destination:C.Cartesian3.fromDegrees(point.longitude_deg,point.latitude_deg,point.elevation_asl_m+this.scene.worldSettings.map_base_height_m),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});}
  }
  update(status) {
    // Restart is a bridge operation and must remain available if MAVLink is lost.
    this.apply.disabled=!!status.restarting || !!this.missions.editor?.draft || !this.select.value;
    this.apply.title=status.restarting?'Дождитесь завершения перезапуска':this.missions.editor?.draft?'Сначала сохраните или отмените редактирование миссии':'Перезапустить полёт на выбранной стартовой площадке';
    const home=status.home,current=[...this.scene.settings.home,this.scene.physicalGroundM,this.scene.settings.heading_deg];
    if(home && !status.restarting && home.some((value,index)=>value!==current[index]) && !this.missions.editor?.draft)location.reload();
  }
}

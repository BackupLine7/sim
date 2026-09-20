import {aircraftHealth} from './aircraft-health.js';
export class AircraftStatus {
  constructor(container) {
    container.innerHTML=`<header>СОСТОЯНИЕ САМОЛЁТА</header>
      <svg viewBox="0 0 280 165" role="img" aria-label="Схема самолёта с индикаторами систем">
        <path d="M140 12 Q148 16 148 36 L150 65 L236 100 L236 112 L150 96 L148 137 L176 150 L176 157 L140 148 L104 157 L104 150 L132 137 L130 96 L44 112 L44 100 L130 65 L132 36 Q132 16 140 12Z" fill="#78999333" stroke="#aac7c2" stroke-width="1.5"/>
        <path d="M120 26 H160 M140 19 V33" stroke="#aac7c2" stroke-width="2"/>
        <g stroke="#aac7c277" fill="none"><path d="M140 30 L105 30 H20"/><path d="M140 70 L178 42 H262"/><path d="M140 99 L98 126 H20"/><path d="M140 128 L183 136 H262"/></g>
        <circle data-light="engine" cx="140" cy="30" r="5"/>
        <circle data-light="gps" cx="140" cy="70" r="5"/>
        <circle data-light="battery" cx="140" cy="99" r="5"/>
        <circle data-light="link" cx="140" cy="128" r="5"/>
        <g fill="#e5efed" font-size="10" font-family="sans-serif">
          <text x="8" y="17">ДВИГАТЕЛЬ</text><text data-value="engine" x="8" y="43">—</text>
          <text x="190" y="28">GPS</text><text data-value="gps" x="190" y="55">—</text>
          <text x="8" y="112">БАТАРЕЯ</text><text data-value="battery" x="8" y="140">—</text>
          <text x="190" y="122">СВЯЗЬ AP</text><text data-value="link" x="190" y="151">—</text>
        </g>
      </svg>
      <div class="aircraft-detail-grid"></div>
      <details class="aircraft-extra-servos"><summary>Дополнительные сервовыходы · мкс</summary><div class="aircraft-servo-grid"></div></details>
      <details class="aircraft-legend"><summary>Обозначения</summary><small class="aircraft-status-note">Цвет — самодиагностика AP: зелёный — исправно, жёлтый — предупреждение, красный — отказ, серый — неизвестно. PWM не подтверждает исправность привода. Батарея в SITL моделируется.</small></details>`;
    this.container=container;
    this.nodes=Object.fromEntries(['engine','gps','battery','link'].map(key=>[key,{light:container.querySelector(`[data-light="${key}"]`),value:container.querySelector(`[data-value="${key}"]`)}]));
    this.rows=[['consumed_mah','Израсходовано',' мА·ч',0]].map(([key,label,unit,digits])=>{
      const row=document.createElement('div'),name=document.createElement('span'),value=document.createElement('b');name.textContent=label;row.append(name,value);container.querySelector('.aircraft-detail-grid').append(row);return {key,unit,digits,value};
    });
    this.servos=Array.from({length:8},(_,index)=>{
      const row=document.createElement('div'),label=document.createElement('span'),value=document.createElement('b');row.append(label,value);container.querySelector('.aircraft-servo-grid').append(row);return {channel:index+1,label,value};
    });
    const svg=container.querySelector('svg');
    this.controlLights={};
    for(const [name,path] of Object.entries({aileron:'M45 107 L100 96 M180 96 L235 107',elevator:'M106 152 L132 141 M148 141 L174 152',rudder:'M140 119 V146'})) {
      const line=document.createElementNS('http://www.w3.org/2000/svg','path');line.setAttribute('d',path);line.setAttribute('stroke-width','4');line.setAttribute('fill','none');svg.append(line);this.controlLights[name]=line;
    }
    this.attachCallouts(svg);
    this.update({});
  }
  attachCallouts(svg) {
    const ns='http://www.w3.org/2000/svg';
    const element=(tag,attributes,parent=svg)=>{const node=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attributes))node.setAttribute(key,value);parent.append(node);return node;};
    for(const node of [...svg.querySelectorAll('g,circle')])node.remove();
    const plane=element('g',{transform:'translate(128 40) scale(1.8)'});
    for(const path of [...svg.querySelectorAll(':scope > path')])plane.append(path);
    svg.setAttribute('viewBox','120 0 520 360');
    this.callouts={};
    // Keep each side ordered from nose to tail so the leaders do not cross.
    const groups=[
      ['engine','ДВИГАТЕЛЬ',8,12,280,106],
      ['sensors','БАРОМЕТР / IMU',8,100,275,157],
      ['aileron','ЭЛЕРОНЫ',8,188,188,185],
      ['elevator','РУЛЬ ВЫСОТЫ',8,276,254,229],
      ['gps','GPS',378,12,280,145],
      ['battery','БАТАРЕЯ',378,100,280,179],
      ['link','АВТОПИЛОТ / СВЯЗЬ',378,188,285,202],
      ['rudder','РУЛЬ НАПРАВЛЕНИЯ',378,276,280,215],
    ];
    for(const [key,title,originalX,y,originalAx,originalAy] of groups) {
      const x=originalX<280?originalX+120:originalX+80;
      const ax=(originalAx-140)*1.8+128,ay=(originalAy-80)*1.8+40;
      const edge=x<380?x+174:x;
      element('path',{d:`M${ax} ${ay} L${edge+(x<380?10:-10)} ${y+30} L${edge} ${y+30}`,fill:'none',stroke:'#8ea9a4','stroke-width':1});
      const light=element('circle',{cx:ax,cy:ay,r:4,fill:'#849498'});
      element('rect',{x,y,width:174,height:84,rx:6,fill:'#10262ded',stroke:'#8ea9a455'});
      const heading=element('text',{x:x+8,y:y+16,fill:'#a9c2bd','font-size':12,'font-family':'sans-serif'});heading.textContent=title;
      const lines=[30,45,60].map(offset=>element('text',{x:x+8,y:y+offset,fill:'#eef5ef','font-size':13,'font-family':'sans-serif'}));
      const healthText=element('text',{x:x+8,y:y+77,'font-size':11,'font-family':'sans-serif'});
      const healthTitle=element('title',{},light);
      this.callouts[key]={lines,light,healthText,healthTitle};
      if(this.nodes[key])this.nodes[key]={light,value:lines[0]};
    }
  }
  set(key,text,color) {this.nodes[key].value.textContent=text;this.nodes[key].light.setAttribute('fill',color);}
  update(status) {
    const now=performance.now();
    if(now-(this.lastUpdateMs ?? -Infinity)<200)return;
    this.lastUpdateMs=now;
    const t={};
    if(status.connected && status.physics_live)for(const [key,value] of Object.entries(status.telemetry || {})) {
      if(key.endsWith('_function') || Date.now()-(status.telemetry_updated_ms?.[key] ?? 0)<5000)t[key]=value;
    }
    const signature=JSON.stringify([t,status.connected,status.physics_live,status.mode,status.armed]);
    if(signature===this.lastSignature)return;
    this.lastSignature=signature;
    const green='#9ae67d',gray='#849498',yellow='#ffcf55';
    this.set('engine',Number.isFinite(t.throttle_pct)?`Газ ${t.throttle_pct}%`:'Нет данных',Number.isFinite(t.throttle_pct)?(t.throttle_pct>0?green:gray):gray);
    this.set('gps',Number.isFinite(t.gps_fix)?`Fix ${t.gps_fix} · ${t.satellites ?? '—'} спут.`:'Нет данных',Number.isFinite(t.gps_fix)?(t.gps_fix>=3?green:yellow):gray);
    this.set('battery',Number.isFinite(t.battery_voltage_v)?`${t.battery_voltage_v.toFixed(1)} В · ${t.battery_remaining_pct ?? '—'}%`:'Нет данных',Number.isFinite(t.battery_voltage_v)?(t.battery_remaining_pct===0?yellow:green):gray);
    this.set('link',status.connected?'Подключена':'Нет связи',status.connected?green:gray);
    for(const row of this.rows)row.value.textContent=Number.isFinite(t[row.key])?t[row.key].toFixed(row.digits)+row.unit:'Нет данных';
    const functions={0:'Не назначен',4:'Элероны',19:'Руль высоты',21:'Руль направления',70:'Газ',77:'Элевон левый',78:'Элевон правый'};
    for(const servo of this.servos) {
      const fn=t[`servo_${servo.channel}_function`],pwm=t[`servo_${servo.channel}_pwm`];
      servo.label.textContent=`CH${servo.channel} · ${functions[fn] ?? (fn===undefined?'Назначение неизвестно':`Функция ${fn}`)}`;
      servo.value.textContent=Number.isFinite(pwm)?`${pwm} мкс`:'Нет данных';
      servo.value.parentElement.hidden=fn===0 || [4,19,21,70].includes(fn) || !Number.isFinite(pwm);
    }
    this.container.querySelector('.aircraft-extra-servos').hidden=this.servos.every(s=>s.value.parentElement.hidden);
    for(const [key,fn] of Object.entries({aileron:4,elevator:19,rudder:21})) {
      const present=this.servos.some(s=>t[`servo_${s.channel}_function`]===fn && Number.isFinite(t[`servo_${s.channel}_pwm`]));
      this.controlLights[key].setAttribute('stroke',present?green:gray);
      const channels=this.servos.filter(s=>t[`servo_${s.channel}_function`]===fn);
      this.callouts[key].light.setAttribute('fill',present?green:gray);
      this.callouts[key].lines[0].textContent=channels.map(s=>`CH${s.channel}: ${t[`servo_${s.channel}_pwm`] ?? '—'} мкс`).join(' · ') || 'Канал не определён';
      this.callouts[key].lines[1].textContent='Команда приводу (PWM)';
      this.callouts[key].lines[2].textContent='Положение: нет данных';
    }
    const fmt=(key,unit,digits=1)=>Number.isFinite(t[key])?t[key].toFixed(digits)+unit:'нет данных';
    this.callouts.engine.lines[1].textContent='RPM: '+fmt('engine_rpm','',0);
    this.callouts.engine.lines[2].textContent=this.servos.filter(s=>t[`servo_${s.channel}_function`]===70).map(s=>`CH${s.channel}: ${t[`servo_${s.channel}_pwm`] ?? '—'} мкс`).join(' · ') || 'PWM: нет данных';
    this.callouts.gps.lines[1].textContent='HDOP: '+fmt('hdop','',2);
    this.callouts.battery.lines[1].textContent='Ток: '+fmt('battery_current_a',' А');
    this.callouts.battery.lines[2].textContent='T: '+fmt('battery_temperature_c',' °C');
    this.callouts.sensors.lines[0].textContent=fmt('pressure_hpa',' гПа')+' · '+fmt('barometer_temperature_c',' °C');
    this.callouts.sensors.lines[1].textContent='Крен: '+fmt('roll_deg','°');
    this.callouts.sensors.lines[2].textContent='Тангаж: '+fmt('pitch_deg','°');
    this.callouts.sensors.light.setAttribute('fill',Number.isFinite(t.pressure_hpa)?green:gray);
    this.callouts.link.lines[1].textContent=status.connected?status.mode:'Нет данных';
    this.callouts.link.lines[2].textContent=status.connected?(status.armed?'ARMED':'DISARMED'):'—';
    const colors={healthy:green,warning:yellow,fault:'#ff6666',unknown:gray};
    for(const [key,health] of Object.entries(aircraftHealth(t,status))) {
      const node=this.callouts[key],color=colors[health.level];
      node.light.setAttribute('fill',color);
      node.healthText.setAttribute('fill',color);
      node.healthText.textContent=health.text.length>26?health.text.slice(0,25)+'…':health.text;
      node.healthTitle.textContent=health.text;
      node.healthText.setAttribute('aria-label',health.text);
      if(this.controlLights[key])this.controlLights[key].setAttribute('stroke',color);
    }

  }
}

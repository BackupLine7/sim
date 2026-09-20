const result=(level,text)=>({level,text});

// MAV_SYS_STATUS_SENSOR bits describe autopilot self-diagnostics, not PWM feedback.
export function systemHealth(t, systems) {
  if (!['present','enabled','health'].every(name=>Number.isInteger(t[`sensors_${name}`])))
    return result('unknown','Нет самодиагностики');
  const missing=[],disabled=[],failed=[];
  for (const [bit,name] of systems) {
    if (!(t.sensors_present & bit)) missing.push(name);
    else if (!(t.sensors_enabled & bit)) disabled.push(name);
    else if (!(t.sensors_health & bit)) failed.push(name);
  }
  if(failed.length) return result('fault','Отказ: '+failed.join(', '));
  if(disabled.length) return result('warning','Отключён: '+disabled.join(', '));
  if(missing.length) return result('unknown','Нет диагностики: '+missing.join(', '));
  return result('healthy','AP: исправно');
}

export function aircraftHealth(t,status) {
  const unknown=result('unknown','Нет обратной связи');
  const health={
    engine:systemHealth(t,[[1073741824,'двигатель']]),
    gps:systemHealth(t,[[32,'GPS']]),
    battery:systemHealth(t,[[33554432,'питание']]),
    sensors:systemHealth(t,[[1,'гироскоп'],[2,'акселерометр'],[8,'барометр']]),
    link:systemHealth(t,[[2097152,'AHRS']]),
    aileron:unknown,elevator:unknown,rudder:unknown,
  };
  if(Number.isFinite(t.gps_fix)&&t.gps_fix<3&&health.gps.level!=='fault')
    health.gps=result('warning','Нет 3D-фиксации');
  if(!status.connected)health.link=result('unknown','Нет связи с AP');
  else if(!status.physics_live)health.link=result('unknown','Нет свежих данных');
  else if(!status.armed && health.link.level==='healthy') {
    const prearm=systemHealth(t,[[268435456,'предполётная проверка']]);
    if(prearm.level==='fault')health.link=result('warning','Pre-arm: не пройден');
  }
  return health;
}

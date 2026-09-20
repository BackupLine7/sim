import {setupCustomAircraft} from './custom-aircraft.js';
export async function setupAircraftSelector(command) {
  const select=document.getElementById('aircraft-select'),button=document.getElementById('aircraft-apply'),message=document.getElementById('aircraft-message');
  try {
    const response=await fetch('/api/aircraft');if(!response.ok)throw new Error('Каталог самолётов недоступен');
    const catalog=await response.json();
    for(const aircraft of catalog.aircraft){const option=document.createElement('option');option.value=aircraft.id;option.textContent=aircraft.name;select.append(option);}
    select.value=catalog.selected;
    const describe=()=>{const a=catalog.aircraft.find(a=>a.id===select.value);document.getElementById('aircraft-description').textContent=`${a.description}. Крейсерское задание: ${a.speeds[1]} км/ч. ${a.basis} Меняются физика JSBSim и внешняя модель. Cessna и F-16 пока показаны упрощёнными силуэтами. Перезапуск завершит текущий полёт.`;};
    select.onchange=describe;describe();
    setupCustomAircraft(catalog,select,describe);
    button.onclick=async()=>{
      button.disabled=true;select.disabled=true;
      const id=select.value;message.textContent='Подготовка самолёта…';
      command('restart',{aircraft_id:id});
      for(let attempt=0;attempt<60;attempt++){
        await new Promise(resolve=>setTimeout(resolve,1000));
        try{const r=await fetch('/data/session.json',{cache:'no-store'});const session=await r.json();if(session.aircraft_id===id){location.reload();return;}}catch{}
      }
      message.textContent='Перезапуск не подтверждён. Проверьте сообщение моста.';button.disabled=false;select.disabled=false;
    };
  }catch(error){message.textContent=error.message;button.disabled=true;}
}

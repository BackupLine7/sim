const panel=document.createElement('details');panel.id='event-log';
panel.innerHTML=`<summary>Журнал событий</summary><div class="log-tools"><input type="search" placeholder="Поиск по слову" aria-label="Поиск в журнале"><select aria-label="Уровень журнала"><option value="">Все уровни</option><option value="log">Лог</option><option value="warning">Предупреждение</option><option value="error">Ошибка</option></select><button type="button">Очистить</button></div><div class="log-rows"></div><small></small>`;
document.querySelector('.primary').append(panel);
const openButton=document.createElement('button');
openButton.type='button';openButton.id='open-event-log';openButton.textContent='☷ Логи';
openButton.setAttribute('aria-controls','event-log');
document.getElementById('open-settings').after(openButton);
openButton.onclick=()=>{
  panel.open=true;
  // Always bring the journal back into view, even after a saved drag position.
  Object.assign(panel.style,{position:'fixed',left:'12px',top:'auto',right:'auto',bottom:'12px',width:'min(660px,calc(100vw - 24px))',zIndex:'30'});
  panel.querySelector('input').focus();
};
const rows=[],search=panel.querySelector('input'),filter=panel.querySelector('select'),body=panel.querySelector('.log-rows');
const labels={log:'ЛОГ',warning:'ПРЕДУПРЕЖДЕНИЕ',error:'ОШИБКА'};
let scheduled=false;
function render(){
  scheduled=false;if(!panel.open)return;
  const atBottom=body.scrollHeight-body.scrollTop-body.clientHeight<30;
  const query=search.value.toLocaleLowerCase();
  const matched=rows.filter(row=>(!filter.value||row.level===filter.value)&&row.text.toLocaleLowerCase().includes(query));
  body.replaceChildren(...matched.map(row=>{
    const node=document.createElement('div');node.className='log-'+row.level;
    node.textContent=`${row.time} · ${labels[row.level]} · ${row.text}`;return node;
  }));
  panel.querySelector('small').textContent=`Показано ${matched.length} из ${rows.length} · последние 1000 событий этой вкладки`;
  if(atBottom)body.scrollTop=body.scrollHeight;
}
export function logEvent(level,text){
  rows.push({level:labels[level]?level:'log',text:String(text),time:new Date().toLocaleTimeString()});
  if(rows.length>1000)rows.splice(0,rows.length-1000);
  if(!scheduled){scheduled=true;setTimeout(render,100);}
}
search.oninput=filter.onchange=render;panel.addEventListener('toggle',render);
panel.querySelector('button').onclick=()=>{rows.length=0;render();};
window.addEventListener('error',event=>logEvent('error',event.message || 'Не удалось загрузить ресурс: '+(event.target?.src || event.target?.href || 'неизвестный')),true);
window.addEventListener('unhandledrejection',event=>logEvent('error',event.reason?.message || event.reason));
for(const [method,level] of [['log','log'],['warn','warning'],['error','error']]){
  const original=console[method].bind(console);
  console[method]=(...args)=>{original(...args);logEvent(level,args.map(value=>{try{return value instanceof Error?value.message:typeof value==='object'?JSON.stringify(value):String(value);}catch{return String(value);}}).join(' '));};
}
const originalFetch=window.fetch.bind(window);
window.fetch=async(...args)=>{
  const url=String(args[0]?.url || args[0]);
  try{
    const response=await originalFetch(...args);
    if(!response.ok)logEvent('error',`HTTP ${response.status}: ${url}`);
    else if(args[1]?.method && args[1].method!=='GET')logEvent('log',`${args[1].method} ${url}: выполнено`);
    return response;
  }catch(error){if(error.name!=='AbortError')logEvent('error',`${url}: ${error.message}`);throw error;}
};
let previous={};
let lastAutopilotId=0;
export function logStatus(status){
  if(status.autopilot_event_id<lastAutopilotId)lastAutopilotId=0;
  for(const event of status.autopilot_events || []){
    if(event.id<=lastAutopilotId)continue;
    logEvent(event.severity<=3?'error':event.severity===4?'warning':'log',`ArduPilot: ${event.text}`);
    lastAutopilotId=event.id;
  }
  for(const key of ['mode','phase','connected','mission_id','mission_next','mission_complete','mission_completed']){
    if(status[key]!==undefined && JSON.stringify(status[key])!==JSON.stringify(previous[key]))logEvent(key==='connected'&&!status[key]?'warning':'log',`${key}: ${JSON.stringify(status[key])}`);
  }
  if(status.notice && status.notice!==previous.notice && !(status.autopilot_events || []).some(event=>event.text===status.notice))logEvent(status.phase==='error'?'error':'log',status.notice);
  previous={...status};
}
logEvent('log','Журнал запущен');

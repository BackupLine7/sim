import { setupBuildingRegions } from './building-regions.js';

export function syncSettingsDialog() {
  const dialog=document.getElementById('settings-dialog');
  const side=['starts','missions'].includes(dialog.dataset.activeTab);
  dialog.classList.toggle('map-editor-settings',side);
  if(!dialog.open)return;
  const modal=dialog.matches(':modal');
  if(modal===!side)return;
  dialog.close();
  if(side)dialog.show();else dialog.showModal();
}
// Reparent existing fields so values and input handlers survive tab switches.
export function setupSettingsTabs(form) {
  const fieldsets=[...form.querySelectorAll(':scope > fieldset')];
  const [map,terrain,controls,aircraft]=fieldsets;
  const createGroup=title=>{
    const group=document.createElement('fieldset'),legend=document.createElement('legend');
    legend.textContent=title;group.append(legend);return group;
  };
  const instruments=createGroup('Приборы'),vegetation=createGroup('Растительность'),weather=createGroup('Погода');
  const move=(group,selector)=>group.append(form.querySelector(selector).closest('label'));
  for(const name of ['compass','horizon','scanner'])move(instruments,`#settings-show-${name}`);
  for(const id of ['settings-roadside','settings-tree-density'])move(vegetation,`#${id}`);
  const treeHelp=[...map.querySelectorAll('small')].find(node=>node.textContent.includes('Ряды и отдельные'));
  if(treeHelp)vegetation.append(treeHelp);
  for(const name of ['wind_speed_m_s','wind_direction_deg'])move(weather,`[name="${name}"]`);
  for(const group of [map,terrain,controls,aircraft,instruments,vegetation,weather])
    for(const input of group.querySelectorAll('input,select,textarea'))input.setAttribute('form',form.id);
  const fleet=createGroup('Выбор самолёта');
  fleet.innerHTML='<label>Самолёт<select id=aircraft-select></select></label><p id=aircraft-description></p><button type=button id=aircraft-apply>Выбрать и перезапустить полёт</button><p id=aircraft-message role=status></p>';
  const starts=createGroup('Стартовые площадки'),missions=createGroup('Создание и редактирование миссий');
  const startPanel=document.querySelector('.start-panel');
  const startChoice=document.createElement('div');startChoice.className='mission-start-choice';
  const startLabel=document.createElement('label');startLabel.htmlFor='start-location';startLabel.textContent='Точка старта';
  const startApply=document.getElementById('start-apply');
  startApply.textContent='Начать здесь';startApply.title='Перезапустить полёт на выбранной стартовой площадке';
  startChoice.append(startLabel,document.getElementById('start-location'),startApply);
  document.querySelector('.mission-panel > summary').after(startChoice);
  startPanel.querySelector('summary').remove();
  starts.append(...startPanel.childNodes);startPanel.remove();
  const savedStarts=document.createElement('label');savedStarts.textContent='Сохранённые точки старта';
  const startList=document.createElement('select');startList.id='settings-start-location';startList.size=5;
  savedStarts.append(startList);
  const startDetails=document.createElement('p');startDetails.id='settings-start-details';
  starts.insertBefore(savedStarts,document.getElementById('start-new'));
  savedStarts.after(startDetails);
  const missionActions=document.getElementById('mission-new').parentElement;
  const missionEditor=document.getElementById('mission-editor');
  missions.append(missionActions,missionEditor);
  const description=document.createElement('p');description.textContent='Для редактирования выберите миссию в полётной панели. Точки добавляются и перемещаются на карте.';missions.prepend(description);
  const mapButton=document.createElement('button');mapButton.type='button';mapButton.id='mission-edit-map';mapButton.textContent='Добавлять и перемещать точки на карте';
  missionEditor.prepend(mapButton);
  const back=document.createElement('button');back.id='return-editor-settings';back.type='button';back.hidden=true;back.textContent='Вернуться к настройкам редактора';document.querySelector('.primary').append(back);
  window.addEventListener('settings-map-edit',event=>{
    back.dataset.tab=event.detail;back.hidden=true;
    document.getElementById(`settings-tab-${event.detail}`).click();
    syncSettingsDialog();
  });
  back.onclick=()=>{if(!document.getElementById('settings-dialog').open)document.getElementById('open-settings').click();document.getElementById(`settings-tab-${back.dataset.tab}`).click();back.hidden=true;window.dispatchEvent(new Event('settings-editor-return'));};
  mapButton.onclick=()=>window.dispatchEvent(new CustomEvent('settings-map-edit',{detail:'missions'}));
  const buildings=createGroup('Здания по областям');setupBuildingRegions(buildings);
  const groups=[['fleet','Выбор самолёта',fleet],['instruments','Приборы',instruments],['map','Карта',map],['vegetation','Растительность',vegetation],['terrain','Рельеф и кеш',terrain],['buildings','Здания по областям',buildings],['controls','Управление',controls],['aircraft','Самолёт и автопилот',aircraft],['weather','Погода',weather],['starts','Точки старта',starts],['missions','Миссии',missions]];
  const tabs=document.createElement('div');tabs.className='settings-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Разделы настроек');
  const body=document.createElement('div');body.className='settings-tab-body';
  map.before(tabs,body);
  const buttons=[];
  function activate(index,focus=false) {
    document.getElementById('settings-dialog').dataset.activeTab=groups[index][0];
    groups.forEach(([, ,group],i)=>{
      group.hidden=i!==index;buttons[i].setAttribute('aria-selected',String(i===index));buttons[i].tabIndex=i===index?0:-1;
    });
    if(focus)buttons[index].focus();
    syncSettingsDialog();
  }
  groups.forEach(([id,title,group],index)=>{
    const button=document.createElement('button');button.type='button';button.textContent=title;button.id=`settings-tab-${id}`;
    button.setAttribute('role','tab');button.setAttribute('aria-controls',`settings-panel-${id}`);
    group.id=`settings-panel-${id}`;group.setAttribute('role','tabpanel');group.setAttribute('aria-labelledby',button.id);
    button.onclick=()=>activate(index);
    button.onkeydown=event=>{
      let next=index;
      if(event.key==='ArrowRight')next=(index+1)%groups.length;
      else if(event.key==='ArrowLeft')next=(index+groups.length-1)%groups.length;
      else if(event.key==='Home')next=0;
      else if(event.key==='End')next=groups.length-1;
      else return;
      event.preventDefault();activate(next,true);
    };
    buttons.push(button);tabs.append(button);body.append(group);
  });
  // Keep the independent start form outside the settings form (no nested forms).
  form.before(form.querySelector('.section-heading'),form.querySelector(':scope > p:not([id])'),tabs,body);
  form.parentElement.addEventListener('invalid',event=>{
    const index=groups.findIndex(([, ,group])=>group.contains(event.target));
    if(index>=0)activate(index);
  },true);
  activate(0);
}

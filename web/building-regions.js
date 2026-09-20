// Region packs are permanent; this panel deliberately does not clear terrain/cache.
export function setupBuildingRegions(panel) {
  panel.innerHTML = `<legend>Здания по областям</legend>
    <p>Все доступные здания в границах выбранной области. Скачанные области хранятся на диске и автоматически используются в 3D-сцене.</p>
    <input type="search" class="building-region-search" aria-label="Поиск области" placeholder="Найти в списке — остальные области остаются видимыми">
    <p class="building-region-message" role="status"></p>
    <button type="button" class="building-region-retry" hidden>Повторить загрузку списка</button>
    <div class="building-region-list"></div>
    <small>Здания: <a href="https://overturemaps.org/attribution/" target="_blank" rel="noopener">Overture Maps · OpenStreetMap и другие источники</a>. Границы: <a href="https://www.geoboundaries.org/" target="_blank" rel="noopener">geoBoundaries</a>. Полнота и высоты зависят от исходных данных.</small>`;
  const search=panel.querySelector('input'), list=panel.querySelector('.building-region-list');
  const message=panel.querySelector('[role=status]'), retry=panel.querySelector('.building-region-retry');
  const countries=new Intl.DisplayNames(['ru'],{type:'region'});
  let snapshot=null, busy=false;
  const sizes=bytes=>bytes>=1024**3?`${(bytes/1024**3).toFixed(2)} ГБ`:`${(bytes/1024**2).toFixed(1)} МБ`;
  function render() {
    if(!snapshot)return;
    retry.hidden=snapshot.state!=='error';
    message.textContent=snapshot.state==='loading'?'Загружаются границы областей… Первый запрос может занять несколько минут.':snapshot.state==='error'?`Не удалось получить список: ${snapshot.error}`:`Областей: ${snapshot.regions.length} · Выпуск ${snapshot.release}`;
    const query=search.value.trim().toLocaleLowerCase();
    const wanted=new Set();
    for(const region of snapshot.regions) {
      const country=region.country?countries.of(region.country):'';
      wanted.add(region.id);
      let row=[...list.children].find(node=>node.dataset.id===region.id);
      if(!row) {
        row=document.createElement('div');row.className='building-region-row';row.dataset.id=region.id;
        const text=document.createElement('div'),name=document.createElement('strong'),details=document.createElement('small'),button=document.createElement('button');
        text.append(name,details);button.type='button';row.append(text,button);list.append(row);
        button.onclick=()=>request({action:button.dataset.action,id:region.id});
      }
      row.querySelector('strong').textContent=`${region.name} · ${country}`;
      row.classList.toggle('building-region-match',Boolean(query&&`${region.name} ${country} ${region.code??''}`.toLocaleLowerCase().includes(query)));
      const active=['queued','loading'].includes(region.state);
      const state=region.state==='queued'?'В очереди':region.state==='loading'?`Загрузка не завершена: обработано ${region.processed.toLocaleString('ru-RU')} зданий. Новая выгрузка появится в сцене после завершения.`:region.state==='error'?`Ошибка: ${region.error}`:region.state==='cancelled'?'Загрузка отменена':'';
      const saved=region.downloaded?`${region.count.toLocaleString('ru-RU')} зданий · ${sizes(region.bytes)} · подключено к 3D-сцене`:'';
      row.querySelector('small').textContent=[state,saved].filter(Boolean).join(' · ')||'Ещё не загружено';
      const button=row.querySelector('button');button.dataset.action=active?'cancel':'download';
      button.textContent=active?'Отменить':region.downloaded?'Обновить':'Скачать';
      button.setAttribute('aria-label',`${button.textContent}: ${region.name}`);
    }
    for(const row of [...list.children])if(!wanted.has(row.dataset.id))row.remove();
  }
  async function request(body) {
    if(busy)return;
    busy=true;
    try {
      const response=await fetch('/api/building-regions',body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
      if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('Сервер загрузчика ещё не обновлён. Требуется перезапуск моста.');
      const data=await response.json();
      if(!response.ok)throw new Error(data.error||response.statusText);
      snapshot=data;render();
    } catch(error) { message.textContent=`Не удалось связаться с загрузчиком: ${error.message}`; }
    finally { busy=false; }
  }
  search.oninput=()=>{render();list.querySelector('.building-region-match')?.scrollIntoView({block:'nearest'});};
  retry.onclick=()=>request({action:'catalog'});
  const visible=()=>!panel.hidden&&document.getElementById('settings-dialog').open;
  new MutationObserver(()=>{if(visible())request();}).observe(panel,{attributes:true,attributeFilter:['hidden']});
  setInterval(()=>{if(visible())request();},2000);
}

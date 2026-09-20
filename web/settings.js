import {setupSettingsTabs,syncSettingsDialog} from './settings-tabs.js';
import {enableSettingsDragging} from './draggable-settings.js';
export class SettingsPanel {
  async load() {
    setupSettingsTabs(document.getElementById('settings-form'));
    enableSettingsDragging(document.getElementById('settings-dialog'));
    const terrainEnabled=document.getElementById('terrain-download-enabled'),terrainClear=document.getElementById('terrain-cache-clear'),terrainStatus=document.getElementById('terrain-cache-status');
    const terrainRequest=async data=>{
      try {
        const response=await fetch('/api/terrain-cache',data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});
        const state=await response.json();if(!response.ok)throw Error(state.error);
        terrainEnabled.checked=state.enabled;terrainClear.disabled=state.pending>0;
        terrainStatus.textContent=`Высоты: ${state.files} файлов · ${state.disk_mb} МБ на диске · ${state.memory_tiles} в памяти · ожидают загрузки: ${state.pending}${Object.keys(state.errors).length?' · есть недоступные участки (используется резервная поверхность)':''}`;
      }catch(error){terrainStatus.textContent=error.message;}
    };
    terrainEnabled.onchange=()=>terrainRequest({enabled:terrainEnabled.checked});
    terrainClear.onclick=()=>terrainRequest({action:'clear'});
    await terrainRequest();
    setInterval(()=>{if(document.getElementById('settings-dialog').open)terrainRequest();},3000);
    const visible = {compass:true, horizon:true, scanner:true};
    try {Object.assign(visible, JSON.parse(localStorage.getItem('flightlab-instruments') || '{}'));} catch {}
    const applyVisibility = () => {
      for (const name of ['compass','horizon','scanner']) document.getElementById(name+'-instrument').hidden = !visible[name];
      document.getElementById('attitude').hidden = !visible.compass && !visible.horizon;
    };
    for (const name of ['compass','horizon','scanner']) {
      const input = document.getElementById('settings-show-'+name);
      input.checked = visible[name] !== false;
      visible[name] = input.checked;
      input.onchange = () => {
        visible[name] = input.checked;
        try {localStorage.setItem('flightlab-instruments', JSON.stringify(visible));} catch {}
        applyVisibility();
      };
    }
    applyVisibility();
    const grid = document.getElementById('settings-map-grid');
    try {grid.checked = localStorage.getItem('flightlab-map-grid') !== 'false';} catch {}
    const applyGrid = () => window.dispatchEvent(new CustomEvent('map-grid-changed', {detail:grid.checked}));
    grid.onchange = () => {
      try {localStorage.setItem('flightlab-map-grid', String(grid.checked));} catch {}
      applyGrid();
    };
    applyGrid();
    const world = await fetch('/api/world/settings').then(response => {
      if (!response.ok) throw new Error('Настройки карты недоступны');
      return response.json();
    });
    const defaults = await fetch('/data/streaming-settings.json').then(response => {
      if (!response.ok) throw new Error('Настройки памяти карты недоступны');
      return response.json();
    });
    let streaming = {...defaults, active_radius_tiles:world.active_radius_tiles, trees_per_tile:world.trees_per_tile};
    try {Object.assign(streaming, JSON.parse(localStorage.getItem('flightlab-streaming') || '{}'));} catch {}
    const retain = document.getElementById('settings-retain-tiles');
    const memory = document.getElementById('settings-tile-memory');
    const radius = document.getElementById('settings-tile-radius');
    const trees = document.getElementById('settings-tree-density');
    const roadside = document.getElementById('settings-roadside');
    roadside.checked = streaming.roadside_enabled !== false;
    trees.value = Number.isSafeInteger(streaming.trees_per_tile) && streaming.trees_per_tile >= 0 ? streaming.trees_per_tile : world.trees_per_tile;
    retain.checked = streaming.retain_loaded_tiles === true;
    memory.value = Number.isFinite(streaming.tile_memory_limit_mb) && streaming.tile_memory_limit_mb > 0 ? streaming.tile_memory_limit_mb : defaults.tile_memory_limit_mb;
    radius.value = Number.isSafeInteger(streaming.active_radius_tiles) && streaming.active_radius_tiles >= 0 ? streaming.active_radius_tiles : world.active_radius_tiles;
    const applyStreaming = () => {
      memory.setCustomValidity(Number.isFinite(memory.valueAsNumber) && memory.valueAsNumber > 0 ? '' : 'Введите положительный лимит памяти');
      radius.setCustomValidity(Number.isSafeInteger(radius.valueAsNumber) && radius.valueAsNumber >= 0 ? '' : 'Введите целое число от нуля');
      trees.setCustomValidity(Number.isSafeInteger(trees.valueAsNumber) && trees.valueAsNumber >= 0 ? '' : 'Введите целое число от нуля');
      if (!memory.checkValidity() || !radius.checkValidity() || !trees.checkValidity()) return;
      streaming = {roadside_enabled:roadside.checked, retain_loaded_tiles:retain.checked, tile_memory_limit_mb:memory.valueAsNumber, active_radius_tiles:radius.valueAsNumber, trees_per_tile:trees.valueAsNumber};
      try {localStorage.setItem('flightlab-streaming', JSON.stringify(streaming));} catch {}
      window.dispatchEvent(new CustomEvent('streaming-settings-changed', {detail:streaming}));
    };
    for (const input of [retain, memory, radius, trees, roadside]) input.addEventListener('change', applyStreaming);
    radius.addEventListener('input',applyStreaming);
    radius.closest('label').title='Радиус предзагрузки ближних и крупных блоков. Уже видимые блоки и район самолёта удерживаются независимо от уменьшения радиуса.';
    applyStreaming();
    const response = await fetch("/api/settings");
    if (!response.ok) throw new Error("Настройки недоступны");
    this.value = await response.json();
    this.envelope = await fetch('/api/aircraft-envelope').then(response=>{if(!response.ok)throw Error('Профиль самолёта недоступен');return response.json();});
    const limit=this.envelope.maximum_commanded_airspeed_kmh;
    for(const name of ['minimum_speed_kmh','cruise_speed_kmh','maximum_speed_kmh','landing_speed_kmh']) {
      const input=document.querySelector(`[name="${name}"]`);input.max=limit;input.title=`Предел задания ${this.envelope.model}: ${limit} км/ч`;
    }
    const dialog = document.getElementById("settings-dialog"),
      form = document.getElementById("settings-form");
    document.getElementById("open-settings").onclick = () => {
      this.onOpen?.();
      this.populate(form);
      if(!dialog.open)dialog.showModal();
      syncSettingsDialog();
    };
    document.getElementById("close-settings").onclick = () => dialog.close();
    form.onsubmit = async (event) => {
      event.preventDefault();
      const value = structuredClone(this.value);
      for (const group of ["controls", "aircraft"])
        for (const [name, previous] of Object.entries(value[group])) {
          const element = form.elements.namedItem(name);
          value[group][name] =
            typeof previous === "boolean"
              ? element.checked
              : typeof previous === "number"
                ? Number(element.value)
                : element.value;
        }
      const notice = document.getElementById("settings-notice");
      try {
        const response = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(value),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error);
        this.value = result;
        window.dispatchEvent(new Event("controls-settings-changed"));
        this.showKeys();
        notice.textContent =
          "Сохранено. Управление применяется сразу; параметры самолёта — после рестарта.";
      } catch (error) {
        notice.textContent = error.message;
      }
    };
    this.showKeys();
  }
  populate(form) {
    for (const group of Object.values(this.value))
      for (const [name, value] of Object.entries(group)) {
        const input = form.elements.namedItem(name);
        if (typeof value === "boolean") input.checked = value;
        else input.value = value;
      }
    document.getElementById("settings-notice").textContent = "";
  }
  showKeys() {
    document.getElementById("key-help").textContent =
      "WASD / стрелки — тангаж и крен · Z/C рыскание · Q/E газ · Space — автопилот";
  }
  axis(name, value) {
    const controls = this.value.controls;
    return (
      value *
      controls[name + "_response"] *
      (controls["invert_" + name] ? -1 : 1)
    );
  }
}

export function setupCustomAircraft(catalog,select,onCreated) {
  const panel=document.createElement('details');
  panel.innerHTML=`<summary>Создать свой самолёт / загрузить GLB</summary>
    <label>Название<input data-field="name" required></label>
    <p>Физика и автопилот копируются с самолёта, выбранного выше. GLB меняет только внешний вид.</p>
    <label>Внешняя модель GLB (необязательно)<input data-field="model" type="file" accept=".glb"></label>
    <label>Масштаб модели<input data-field="scale" type="number" min="0.000001" step="any" value="1" required></label>
    <p>GLB: встроенные текстуры, единицы — метры, нос вдоль +X, верх +Z. Начало модели — точка опоры на земле.</p>
    <button type="button">Создать самолёт</button><p role="status"></p>`;
  document.getElementById('aircraft-message').after(panel);
  const button=panel.querySelector('button'),message=panel.querySelector('[role=status]');
  button.onclick=async()=>{
    const name=panel.querySelector('[data-field=name]'),scale=panel.querySelector('[data-field=scale]');
    if(!name.reportValidity() || !scale.reportValidity())return;
    button.disabled=true;message.textContent='Сохранение самолёта…';
    try {
      const file=panel.querySelector('[data-field=model]').files[0];
      const data={name:name.value.trim(),base_id:select.value,scale:scale.valueAsNumber};
      if(file)data.glb_base64=await new Promise((resolve,reject)=>{
        const reader=new FileReader();reader.onerror=()=>reject(Error('Не удалось прочитать файл'));
        reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(file);
      });
      const response=await fetch('/api/aircraft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      if(!response.headers.get('content-type')?.includes('application/json'))throw Error('Для импорта требуется обновлённый мост');
      const aircraft=await response.json();if(!response.ok)throw Error(aircraft.error);
      catalog.aircraft.push(aircraft);select.add(new Option(aircraft.name,aircraft.id));select.value=aircraft.id;onCreated();
      message.textContent='Самолёт создан. Нажмите «Выбрать и перезапустить полёт», чтобы использовать его.';
    }catch(error){message.textContent=error.message;}finally{button.disabled=false;}
  };
}

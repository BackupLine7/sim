export function setupMovablePanels() {
  const specs=[['#aircraft-status','Состояние самолёта'],['.telemetry-panel','Телеметрия'],['.mission-panel','Миссия'],['.controls','Управление'],['#horizon-instrument','Горизонт'],['#compass-instrument','Компас'],['#scanner-instrument','3D-сканер']];
  specs.push(['#event-log','Журнал событий']);
  for(const [selector,title] of specs) {
    const panel=document.querySelector(selector);
    if(!panel)continue;
    const key='flightlab-panel:'+selector;
    let saved={};try{saved=JSON.parse(localStorage.getItem(key))||{};}catch{}
    const persist=()=>{try{localStorage.setItem(key,JSON.stringify(saved));}catch{}};
    panel.classList.add('movable-panel');
    let handle;
    if(panel.tagName==='DETAILS') {
      handle=panel.querySelector('summary');
      if(typeof saved.open==='boolean')panel.open=saved.open;
      panel.addEventListener('toggle',()=>{saved.open=panel.open;persist();});
    } else if(selector==='.controls') {
      handle=panel.querySelector('.section-heading');
      const body=panel.querySelector('#control-body');
      body.hidden=!!saved.folded;
      panel.querySelector('#toggle-controls').addEventListener('click',()=>{saved.folded=body.hidden;persist();});
    } else {
      if(selector==='#aircraft-status')panel.querySelector(':scope > header')?.remove();
      const body=document.createElement('div');
      while(panel.firstChild)body.append(panel.firstChild);
      handle=document.createElement('div');handle.className='panel-handle';
      const button=document.createElement('button');button.type='button';
      const fold=()=>{body.hidden=!!saved.folded;button.textContent=(body.hidden?'▸ ':'▾ ')+title;button.setAttribute('aria-expanded',String(!body.hidden));};
      button.onclick=()=>{saved.folded=!saved.folded;fold();persist();};
      handle.append(button);panel.append(handle,body);fold();
    }
    handle.classList.add('panel-drag-handle');
    handle.title='Перетащите для перемещения · двойной щелчок по свободному месту — вернуть положение';
    const position=(x,y)=>{
      // Freeze the dock-relative width before fixed positioning makes 100%
      // refer to the viewport (also when restoring a saved position).
      if(panel.style.position!=='fixed')panel.style.width=panel.getBoundingClientRect().width+'px';
      const rect=panel.getBoundingClientRect();
      saved.x=Math.max(0,Math.min(x,innerWidth-rect.width));
      saved.y=Math.max(0,Math.min(y,innerHeight-Math.min(rect.height,innerHeight)));
      Object.assign(panel.style,{position:'fixed',left:saved.x+'px',top:saved.y+'px',right:'auto',bottom:'auto',margin:'0',zIndex:'25'});
    };
    if(Number.isFinite(saved.x)&&Number.isFinite(saved.y))requestAnimationFrame(()=>position(saved.x,saved.y));
    let drag=null,moved=false;
    handle.addEventListener('pointerdown',event=>{
      if(event.button!==0 || event.target.closest('input,select'))return;
      const rect=panel.getBoundingClientRect();drag={x:event.clientX,y:event.clientY,left:rect.left,top:rect.top};moved=false;
    });
    handle.addEventListener('pointermove',event=>{
      if(!drag)return;
      const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
      if(!moved&&Math.hypot(dx,dy)<4)return;
      if(!moved){panel.style.width=panel.getBoundingClientRect().width+'px';handle.setPointerCapture(event.pointerId);}
      moved=true;position(drag.left+dx,drag.top+dy);
    });
    const stop=()=>{if(drag&&moved)persist();drag=null;};
    handle.addEventListener('pointerup',stop);handle.addEventListener('pointercancel',stop);handle.addEventListener('lostpointercapture',stop);
    handle.addEventListener('click',event=>{if(moved){event.preventDefault();event.stopImmediatePropagation();moved=false;}},true);
    handle.addEventListener('dblclick',event=>{if(event.target.closest('button'))return;delete saved.x;delete saved.y;panel.removeAttribute('style');persist();});
    window.addEventListener('resize',()=>{if(Number.isFinite(saved.x))position(saved.x,saved.y);});
  }
}

export function enableSettingsDragging(dialog) {
  const handle=dialog.querySelector('.section-heading');
  let drag=null;
  function place(left,top) {
    const rect=dialog.getBoundingClientRect();
    dialog.style.margin='0';dialog.style.right='auto';dialog.style.bottom='auto';
    dialog.style.left=`${Math.max(0,Math.min(left,window.innerWidth-rect.width))}px`;
    dialog.style.top=`${Math.max(0,Math.min(top,window.innerHeight-rect.height))}px`;
    dialog.style.setProperty('--settings-top',dialog.style.top);
  }
  handle.addEventListener('pointerdown',event=>{
    if(event.button!==0 || event.target.closest('button'))return;
    const rect=dialog.getBoundingClientRect();
    drag={id:event.pointerId,x:event.clientX-rect.left,y:event.clientY-rect.top};
    handle.setPointerCapture(event.pointerId);event.preventDefault();
    place(rect.left,rect.top);
  });
  handle.addEventListener('pointermove',event=>{
    if(drag && drag.id===event.pointerId)place(event.clientX-drag.x,event.clientY-drag.y);
  });
  const release=()=>{
    if(drag && handle.hasPointerCapture(drag.id))handle.releasePointerCapture(drag.id);
    drag=null;
  };
  handle.addEventListener('pointerup',release);
  handle.addEventListener('pointercancel',release);
  handle.addEventListener('lostpointercapture',()=>{drag=null;});
  dialog.addEventListener('close',release);
  window.addEventListener('blur',release);
  window.addEventListener('resize',()=>{if(dialog.open){const rect=dialog.getBoundingClientRect();place(rect.left,rect.top);}});
}

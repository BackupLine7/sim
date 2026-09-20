export function enableMapDragging(panel, handle) {
  const container = panel.parentElement;
  const storageKey = 'flightlab-map-vertical-position';
  let fraction = null, drag = null;
  const expanded = () => container.classList.contains('map-expanded');
  const availableHeight = () => Math.max(0, container.clientHeight - panel.offsetHeight);
  const place = () => {
    if (fraction !== null && !expanded())
      panel.style.setProperty('--map-top', `${fraction * availableHeight()}px`);
  };
  const move = top => {
    const height = availableHeight();
    fraction = height ? Math.max(0, Math.min(1, top / height)) : 0;
    place();
  };
  const save = () => {
    try {localStorage.setItem(storageKey, String(fraction));} catch {}
  };
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved !== null && Number.isFinite(Number(saved)))
      fraction = Math.max(0, Math.min(1, Number(saved)));
  } catch {}
  handle.addEventListener('pointerdown', event => {
    if (expanded() || event.button !== 0 || event.target.closest('button,select,input')) return;
    drag = {pointerId:event.pointerId, y:event.clientY, top:panel.offsetTop};
    handle.setPointerCapture(event.pointerId);
    handle.classList.add('dragging');
    event.preventDefault();
  });
  handle.addEventListener('pointermove', event => {
    if (drag && event.pointerId === drag.pointerId && !expanded())
      move(drag.top + event.clientY - drag.y);
  });
  const finish = event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    drag = null;
    handle.classList.remove('dragging');
    if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
    if (fraction !== null) save();
  };
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) handle.addEventListener(name, finish);
  handle.addEventListener('keydown', event => {
    if (event.target !== handle || expanded() || !['ArrowUp','ArrowDown','Home','End'].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    const step = handle.offsetHeight;
    move(event.key === 'Home' ? 0 : event.key === 'End' ? availableHeight() : panel.offsetTop + (event.key === 'ArrowUp' ? -step : step));
    save();
  });
  const observer = new ResizeObserver(place);
  observer.observe(container);
  observer.observe(panel);
  place();
}

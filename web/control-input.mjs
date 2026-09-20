const aliases = {
  KeyW: "ArrowUp",
  KeyS: "ArrowDown",
  KeyA: "ArrowLeft",
  KeyD: "ArrowRight",
};
export function isControlPressed(keys, key) {
  return (
    keys.has(key) || (aliases[key] !== undefined && keys.has(aliases[key]))
  );
}

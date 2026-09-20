export function nearbyTiles(longitude, latitude, settings) {
  const z = settings.detail_level, n = 2 ** z;
  const x = Math.floor(((longitude + 180) / 360) * n);
  const y = Math.floor(((1 - Math.asinh(Math.tan((latitude * Math.PI) / 180)) / Math.PI) / 2) * n);
  const radius = settings.active_radius_tiles;
  const candidates = [];
  for (let dx = -radius; dx <= radius; dx++)
    for (let dy = -radius; dy <= radius; dy++)
      candidates.push({ key: `${z}/${x + dx}/${y + dy}`, distance: dx * dx + dy * dy });
  return candidates
    .sort((a, b) => a.distance - b.distance)
    .slice(0, settings.max_resident_tiles)
    .map((item) => item.key);
}

export function terrainCoverage(longitude, latitude, settings) {
  return terrainCoverageForPositions([{longitude_deg:longitude,latitude_deg:latitude}],settings);
}

export function terrainCoverageForPositions(positions, settings) {
  const near = [...new Set(positions.flatMap(p=>nearbyTiles(p.longitude_deg,p.latitude_deg,settings)))];
  if (settings.uniform_tiles) return near;
  if (settings.distant_terrain_level === undefined) return near;
  const coarse = new Set(positions.flatMap(p=>nearbyTiles(p.longitude_deg,p.latitude_deg, {
    detail_level: settings.distant_terrain_level,
    active_radius_tiles: settings.distant_terrain_radius_tiles,
    max_resident_tiles: (2 * settings.distant_terrain_radius_tiles + 1) ** 2,
  })));
  const ancestors = new Set();
  for (const key of near) {
    let [z, x, y] = key.split('/').map(Number);
    while (z > settings.distant_terrain_level) {
      z--; x = Math.floor(x / 2); y = Math.floor(y / 2);
      ancestors.add(`${z}/${x}/${y}`);
    }
  }
  const leaves = new Set(near);
  function visit(key) {
    if (!ancestors.has(key)) { leaves.add(key); return; }
    const [z, x, y] = key.split('/').map(Number);
    for (let dy = 0; dy < 2; dy++) for (let dx = 0; dx < 2; dx++)
      visit(`${z + 1}/${x * 2 + dx}/${y * 2 + dy}`);
  }
  coarse.forEach(visit);
  return [...leaves];
}

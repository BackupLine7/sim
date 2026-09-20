import { terrainCoverageForPositions } from './coverage.mjs';
import { containsTile, visibleLoadedTiles } from './tile-keys.mjs';

const RELOAD_INTERVAL_MS = 500;
const FAILURE_COOLDOWN_MS = 10000;

export class WorldStreamer {
  constructor(host, settings) {
    this.host = host;
    this.settings = settings;
    this.resident = new Map();
    this.pending = new Map();
    this.failed = new Map();
    this.desired = new Set();
    this.loaded = 0;
    this.evicted = 0;
    this.discarded = 0;
    this.debug = false;
    this.lastUpdate = -Infinity;
  }

  configure(preferences) {
    if (['trees_per_tile', 'roadside_enabled'].some(key => preferences[key] !== undefined && preferences[key] !== this.settings[key])) {
      for (const controller of this.pending.values()) controller.abort();
      for (const record of this.resident.values()) { record.tile.destroy(); this.evicted++; }
      this.resident.clear();
      this.failed.clear();
    }
    this.settings = {
      ...this.settings, ...preferences,
      distant_terrain_radius_tiles: preferences.active_radius_tiles ?? this.settings.distant_terrain_radius_tiles,
      max_resident_tiles: (2 * preferences.active_radius_tiles + 1) ** 2,
    };
    this.lastUpdate = -Infinity;
    if (this.lastPose) this.update(this.lastPose, this.lastAdditionalPositions);
    else this.trim();
  }

  setTerrainRevision(revision) {
    if (revision === undefined || revision === this.terrainRevision) return;
    this.terrainRevision = revision;
    this.failed.clear();
    this.pump();
  }

  memoryBytes() {
    return [...this.resident.values()].reduce((sum, record) => sum + (record.tile.memory_bytes || 0), 0);
  }

  trim() {
    const visible = visibleLoadedTiles(this.desired, new Set(this.resident.keys()));
    for (const [key, record] of this.resident) record.tile.setVisible(visible.has(key), this.debug);
    let bytes = this.memoryBytes();
    const limit = this.settings.tile_memory_limit_mb * 1024 * 1024;
    const candidates = [...this.resident].filter(([key]) => !this.desired.has(key) && !visible.has(key))
      .sort((a, b) => (a[1].last_used_ms || 0) - (b[1].last_used_ms || 0));
    for (const [key, record] of candidates) {
      if (this.settings.retain_loaded_tiles && this.desired.size && bytes <= limit) break;
      record.tile.destroy();
      this.resident.delete(key);
      bytes -= record.tile.memory_bytes || 0;
      this.evicted++;
    }
  }

  update(pose, additionalPositions = []) {
    this.lastPose = pose;
    this.lastAdditionalPositions = additionalPositions;
    if (performance.now() - this.lastUpdate < RELOAD_INTERVAL_MS) return;
    this.lastUpdate = performance.now();
    const [w, s, e, n] = this.settings.bounds;
    const positions = [pose, ...additionalPositions]
      .filter(p => p.longitude_deg >= w && p.longitude_deg <= e && p.latitude_deg >= s && p.latitude_deg <= n);
    this.desired = new Set(terrainCoverageForPositions(positions, this.settings));
    const volume = this.host.cullingVolume?.();
    if (volume) {
      const candidates = [...this.resident].sort((a, b) => Number(b[0].split('/')[0]) - Number(a[0].split('/')[0]));
      for (const [key, record] of candidates) {
        if (record.tile.boundingSphere && volume.contains(record.tile.boundingSphere)
          && ![...this.desired].some(other => containsTile(key, other) || containsTile(other, key)))
          this.desired.add(key);
      }
    }
    for (const key of this.desired) {
      const record = this.resident.get(key);
      if (record) record.last_used_ms = performance.now();
    }
    this.trim();
    for (const [key, controller] of this.pending)
      if (!this.desired.has(key)) controller.abort();
    for (const key of this.failed.keys())
      if (!this.desired.has(key)) this.failed.delete(key);
    this.pump();
  }

  pump() {
    for (const key of this.desired) {
      if (this.pending.size >= this.settings.parallel_requests) break;
      if ((this.resident.has(key) && this.resident.get(key).terrainRevision === this.terrainRevision)
        || this.pending.has(key)
        || (this.failed.get(key) || 0) > performance.now())
        continue;
      const controller = new AbortController();
      this.pending.set(key, controller);
      this.load(key, controller).finally(() => {
        this.pending.delete(key);
        this.pump();
      });
    }
  }

  chunkUrl(key) {
    const detailed = Number(key.split('/')[0]) === this.settings.detail_level;
    const trees = detailed ? this.settings.trees_per_tile : 0;
    const roadside = detailed && this.settings.roadside_enabled !== false;
    return `/api/world/chunk/${key}?trees_per_tile=${trees}&roadside=${roadside}`;
  }

  async load(key, controller) {
    const terrainRevision = this.terrainRevision;
    try {
      const response = await fetch(this.chunkUrl(key), { signal: controller.signal });
      if (!response.ok) throw new Error('Нет локального участка');
      const data = await response.json();
      const signature = JSON.stringify([data.bounds, data.source_level, data.terrain?.heights_m, data.buildings, data.trees]);
      const existing = this.resident.get(key);
      if (existing?.signature === signature) {
        existing.terrainRevision = terrainRevision;
        return;
      }
      const imageResponse = await fetch(data.image_url, { signal: controller.signal });
      if (!imageResponse.ok) throw new Error('Нет изображения');
      const bitmap = await createImageBitmap(await imageResponse.blob());
      if (!this.desired.has(key) || controller.signal.aborted) {
        bitmap.close();
        this.discarded++;
        return;
      }
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      canvas.getContext('2d').drawImage(bitmap, 0, 0);
      bitmap.close();
      const record = {
        tile: this.host.createTile(data, canvas),
        data, signature, terrainRevision,
        last_used_ms: performance.now(),
      };
      this.resident.get(key)?.tile.destroy();
      this.resident.set(key, record);
      this.loaded++;
      this.trim();
    } catch (error) {
      if (error.name !== 'AbortError')
        this.failed.set(key, performance.now() + FAILURE_COOLDOWN_MS);
    }
  }

  setDebug(enabled) {
    this.debug = enabled;
    for (const record of this.resident.values()) record.tile.setVisible(record.tile.visible, enabled);
  }

  statistics() {
    const records = [...this.resident.values()];
    const detailed = records.filter(record => record.data.source_level === this.settings.detail_level).length;
    const trees = records.reduce((sum, record) => sum + record.data.trees.length, 0);
    const osmTrees = records.reduce((sum, record) => sum + (record.data.osm_tree_count || 0), 0);
    const active = [...this.resident.keys()].filter(key => this.desired.has(key)).length;
    const memoryMb = this.memoryBytes() / 1024 / 1024;
    const budget = this.settings.retain_loaded_tiles ? ` / ${this.settings.tile_memory_limit_mb} МБ` : '';
    const overflow = this.settings.retain_loaded_tiles && memoryMb > this.settings.tile_memory_limit_mb
      ? ' · активный радиус превышает лимит' : '';
    return `Участки ${active}/${this.desired.size} · сохранено ${this.resident.size - active} · запросы ${this.pending.size}/${this.settings.parallel_requests}\n`
      + `Память ≈ ${memoryMb.toFixed(1)} МБ${budget}${overflow}\n`
      + `Загружено ${this.loaded} · выгружено ${this.evicted} · отменено ${this.discarded}\n`
      + `Детальные ${detailed} · обзорные ${this.resident.size - detailed} · деревья ${trees} (OSM ${osmTrees})\n`
      + `Загрузка следует за самолётом, не за камерой${this.failed.size ? ' · нет части данных' : ''}`;
  }
}

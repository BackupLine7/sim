import { hasTerrain, terrainHeightRangeM, terrainMeshPrimitive, flatImageryRectangle } from './layers/terrain.js';
import { buildingInstances, buildingMemoryBytes } from './layers/buildings.js';
import { treeInstances, treeMemoryBytes } from './layers/vegetation.js';
import { tileOutlinePositions } from './outline.mjs';

const C = window.Cesium;
const TEXTURE_BYTES_PER_PIXEL = 4;
const MIPMAP_FACTOR = 1 + (2 * 4) / 3;
const TERRAIN_BYTES_PER_VERTEX = 200;

function estimateTileMemoryBytes(data, image) {
  return Math.ceil(image.width * image.height * TEXTURE_BYTES_PER_PIXEL * MIPMAP_FACTOR)
    + new TextEncoder().encode(JSON.stringify(data)).byteLength
    + (hasTerrain(data) ? data.terrain.size ** 2 * TERRAIN_BYTES_PER_VERTEX : 0)
    + treeMemoryBytes(data.trees)
    + buildingMemoryBytes(data.buildings);
}

export class CesiumWorldHost {
  constructor({ main, map, groundM }) {
    this.main = main;
    this.map = map;
    this.groundM = groundM;
  }

  cullingVolume() {
    const camera = this.main?.camera;
    if (!camera) return null;
    const frustum = camera.frustum.computeCullingVolume(camera.positionWC, camera.directionWC, camera.upWC);
    return { contains: sphere => frustum.computeVisibility(sphere) !== C.Intersect.OUTSIDE };
  }

  createTile(data, image) {
    const groundM = this.groundM;
    const entities = [];
    const primitives = [];
    const mapPrimitives = [];
    const main = this.main;
    const map = this.map;

    if (hasTerrain(data)) {
      primitives.push(main.scene.primitives.add(terrainMeshPrimitive(data, image)));
      mapPrimitives.push(map.scene.primitives.add(terrainMeshPrimitive(data, image)));
    } else {
      for (const viewer of [main, map])
        entities.push([viewer, viewer.entities.add(flatImageryRectangle(data, image, groundM))]);
    }

    const [minimumM, maximumM] = terrainHeightRangeM(data, groundM);
    const boundingSphere = C.BoundingSphere.fromRectangle3D(
      C.Rectangle.fromDegrees(...data.bounds), C.Ellipsoid.WGS84, (minimumM + maximumM) / 2);
    boundingSphere.radius += (maximumM - minimumM) / 2;

    const outline = main.entities.add({
      show: false,
      polyline: {
        positions: C.Cartesian3.fromDegreesArrayHeights(tileOutlinePositions(data, groundM, 3)),
        arcType: hasTerrain(data) ? C.ArcType.NONE : C.ArcType.GEODESIC,
        width: 3,
        material: C.Color.CYAN,
      },
    });
    const mapOutline = map.entities.add({ show: false, polyline: outline.polyline.clone() });
    entities.push([main, outline], [map, mapOutline]);

    const instances = [
      ...buildingInstances(data.buildings, groundM),
      ...treeInstances(data.trees, groundM),
    ];
    if (instances.length)
      primitives.push(main.scene.primitives.add(new C.Primitive({
        geometryInstances: instances,
        appearance: new C.PerInstanceColorAppearance({ translucent: false, closed: true }),
        asynchronous: true,
        shadows: C.ShadowMode.ENABLED,
      })));

    return {
      memory_bytes: estimateTileMemoryBytes(data, image),
      boundingSphere,
      visible: true,
      setVisible(visible, debug) {
        this.visible = visible;
        for (const [, entity] of entities) entity.show = visible;
        for (const primitive of [...primitives, ...mapPrimitives]) primitive.show = visible;
        outline.show = mapOutline.show = visible && Boolean(debug);
      },
      destroy() {
        for (const [viewer, entity] of entities) viewer.entities.remove(entity);
        for (const primitive of primitives) main.scene.primitives.remove(primitive);
        for (const primitive of mapPrimitives) map.scene.primitives.remove(primitive);
        image.width = image.height = 1;
      },
    };
  }
}

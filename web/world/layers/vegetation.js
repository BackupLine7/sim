const C = window.Cesium;

export const TREE_COLOR = '#405a32';
export const TREE_MEMORY_BYTES = 4096;

export function treeInstances(trees, groundM, color = TREE_COLOR) {
  return trees.map(([lon, lat, height, treeGroundM = groundM]) => new C.GeometryInstance({
    modelMatrix: C.Transforms.eastNorthUpToFixedFrame(
      C.Cartesian3.fromDegrees(lon, lat, treeGroundM + height * 0.5),
    ),
    geometry: new C.CylinderGeometry({
      length: height,
      topRadius: 0.25,
      bottomRadius: height * 0.32,
      slices: 7,
      vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT,
    }),
    attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(C.Color.fromCssColorString(color)) },
  }));
}

export function treeMemoryBytes(trees) {
  return trees.length * TREE_MEMORY_BYTES;
}

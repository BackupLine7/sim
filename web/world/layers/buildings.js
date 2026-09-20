const C = window.Cesium;

export const BUILDING_COLOR = '#b9b5a5';

export function buildingInstances(buildings, groundM, color = BUILDING_COLOR) {
  return buildings.map(building => new C.GeometryInstance({
    geometry: new C.PolygonGeometry({
      polygonHierarchy: new C.PolygonHierarchy(
        C.Cartesian3.fromDegreesArray(building.coordinates.flat()),
        (building.holes ?? []).map(ring => new C.PolygonHierarchy(C.Cartesian3.fromDegreesArray(ring.flat()))),
      ),
      height: building.ground_m ?? groundM,
      extrudedHeight: (building.ground_m ?? groundM) + building.height_m,
      vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT,
    }),
    attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(C.Color.fromCssColorString(color)) },
  }));
}

export function buildingMemoryBytes(buildings) {
  return buildings.reduce((sum, building) => sum + building.coordinates.length * 1024, 0);
}

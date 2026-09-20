const C=window.Cesium;

// Surface distance is independent of map zoom and the route's flight altitude.
export function addMissionLegLabel(entities,start,end) {
  const a=C.Cartographic.fromCartesian(start),b=C.Cartographic.fromCartesian(end);
  const line=new C.EllipsoidGeodesic(a,b);
  const distance=line.surfaceDistance;
  if(!Number.isFinite(distance)||distance<.01)return;
  const midpoint=line.interpolateUsingFraction(.5);
  entities.add({
    position:C.Cartesian3.fromRadians(midpoint.longitude,midpoint.latitude,(a.height+b.height)/2),
    label:{
      text:distance<1000?`${Math.round(distance)} м`:`${(distance/1000).toFixed(2)} км`,
      font:'12px sans-serif',fillColor:C.Color.WHITE,
      showBackground:true,backgroundColor:C.Color.fromCssColorString('#102126dd'),
      pixelOffset:new C.Cartesian2(0,-10),disableDepthTestDistance:Infinity,
    },
  });
}

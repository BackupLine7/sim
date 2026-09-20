import {aircraftBasis} from './flight-math.mjs';
import {missionHeightM} from './mission-height.mjs';
const radians = degrees => degrees*Math.PI/180;
export function scannerContact(pose, point, homeAltitude_m) {
  const lat = radians(pose.latitude_deg), lon = radians(pose.longitude_deg);
  const targetLat = radians(point.latitude_deg), targetLon = radians(point.longitude_deg);
  const radius_m = 6378137;
  const targetHeight_m=missionHeightM(point,homeAltitude_m);
  const targetRadius_m = radius_m + targetHeight_m;
  const ownRadius_m = radius_m + pose.altitude_asl_m;
  const delta = [
    targetRadius_m*Math.cos(targetLat)*Math.cos(targetLon)-ownRadius_m*Math.cos(lat)*Math.cos(lon),
    targetRadius_m*Math.cos(targetLat)*Math.sin(targetLon)-ownRadius_m*Math.cos(lat)*Math.sin(lon),
    targetRadius_m*Math.sin(targetLat)-ownRadius_m*Math.sin(lat),
  ];
  const dot = (a,b) => a.reduce((sum,value,index)=>sum+value*b[index],0);
  const enu = [dot(delta,[-Math.sin(lon),Math.cos(lon),0]), dot(delta,[-Math.sin(lat)*Math.cos(lon),-Math.sin(lat)*Math.sin(lon),Math.cos(lat)]), dot(delta,[Math.cos(lat)*Math.cos(lon),Math.cos(lat)*Math.sin(lon),Math.sin(lat)])];
  const basis = aircraftBasis(radians(pose.yaw_deg), radians(pose.pitch_deg), radians(pose.roll_deg));
  return {right_m:dot(enu,basis.right), forward_m:dot(enu,basis.forward), up_m:dot(enu,basis.up), distance_m:Math.hypot(...delta), height_difference_m:targetHeight_m-pose.altitude_asl_m};
}
export function scaleContact(contact, range_m) {
  const scale = 1/Math.max(range_m, contact.distance_m);
  return {x:contact.right_m*scale, y:contact.forward_m*scale, z:contact.up_m*scale, outside:contact.distance_m>range_m};
}

export function scannerGround(pose, range_m) {
  const distance_m = pose.altitude_agl_m;
  if (!Number.isFinite(distance_m) || !Number.isFinite(range_m) || range_m <= 0) return null;
  const basis = aircraftBasis(radians(pose.yaw_deg), radians(pose.pitch_deg), radians(pose.roll_deg));
  const depth = Math.max(-1, Math.min(1, distance_m/range_m));
  const transform = (east,north,up) => [basis.right,basis.forward,basis.up].map(axis => axis[0]*east+axis[1]*north+axis[2]*up);
  const outside = Math.abs(distance_m) > range_m;
  const radius = Math.sqrt(Math.max(0,1-depth*depth));
  const rim = outside ? [] : Array.from({length:49}, (_,i) => {
    const angle = i/48*Math.PI*2;
    return transform(radius*Math.cos(angle),radius*Math.sin(angle),-depth);
  });
  return {distance_m, outside, foot:transform(0,0,-depth), rim};
}

// Goal heights are absolute terrain MSL, never an offset from the airfield.
export function missionHeightM(point, homeAltitude_m) {
  return point.type==='goal' ? (point.terrain_elevation_asl_m ?? NaN) : homeAltitude_m+point.altitude_relative_m;
}

export const MISSION_COLORS = {completed:'#92989e', current:'#64e572', future:'#ffd84d', goal:'#ff4545'};
export function missionPointColor(index, next, completed) {
  return MISSION_COLORS[(completed ? completed.has(index) : index < next) ? 'completed' : index === next ? 'current' : 'future'];
}

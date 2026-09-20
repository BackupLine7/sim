export function visualGroundCorrection(pose, settings, supportPoints) {
  if (
    pose.altitude_agl_m > 2 ||
    Math.abs(pose.roll_deg) > 30 ||
    Math.abs(pose.pitch_deg) > 30
  )
    return 0;
  const pitch = (pose.pitch_deg * Math.PI) / 180,
    roll = (pose.roll_deg * Math.PI) / 180;
  const up = [
    Math.sin(pitch),
    Math.cos(pitch) * Math.sin(roll),
    Math.cos(pitch) * Math.cos(roll),
  ];
  let lowest = Infinity;
  for (const point of supportPoints)
    lowest = Math.min(
      lowest,
      point[0] * up[0] + point[1] * up[1] + point[2] * up[2],
    );
  return Math.max(
    0,
    settings.runway_visual_height_m +
      settings.model_surface_clearance_m -
      pose.altitude_agl_m -
      settings.aircraft_visual_origin_up_m * up[2] -
      lowest * settings.aircraft_visual_scale,
  );
}

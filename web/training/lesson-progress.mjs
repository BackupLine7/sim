export const TYPE_LABELS = {takeoff:'Взлёт', transit:'Транзит', goal:'Цель занятия', maneuver:'Манёвр'};

// This lesson model uses fictional local coordinates only; no geographic or flight-control API.
export class LessonProgress {
  constructor(lesson) { this.lesson = lesson; this.next = 0; }
  get complete() { return this.next === this.lesson.waypoints.length; }
  update(position) {
    if (this.complete) return false;
    const point = this.lesson.waypoints[this.next];
    const distance = Math.hypot(position.x_m-point.x_m, position.y_m-point.y_m);
    if (distance > point.radius_m || Math.abs(position.height_m-point.height_m) > this.lesson.height_tolerance_m) return false;
    this.next++;
    return true;
  }
  segmentComplete(index) { return index + 1 < this.next; }
}

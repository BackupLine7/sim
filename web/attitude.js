export class AttitudeIndicator {
  constructor() {
    this.horizon = document.getElementById("attitude-horizon");
    this.readout = document.getElementById("attitude-readout");
    this.compass = document.getElementById('heading-rose');
    this.headingReadout = document.getElementById('heading-readout');
  }
  update(pose) {
    // Bank rotates the earth opposite the aircraft; nose-up lowers the horizon.
    this.horizon.style.transform = `rotate(${-pose.roll_deg}deg) translateY(${Math.max(-60, Math.min(60, pose.pitch_deg)) * 1.3}px)`;
    this.readout.textContent = `Крен ${pose.roll_deg.toFixed(0)}° · Тангаж ${pose.pitch_deg.toFixed(0)}°`;
    const heading_deg = ((pose.yaw_deg % 360) + 360) % 360;
    this.compass.setAttribute('transform', `rotate(${-heading_deg} 60 60)`);
    this.headingReadout.textContent = `Курс ${String(Math.round(heading_deg) % 360).padStart(3, '0')}°`;
  }
}

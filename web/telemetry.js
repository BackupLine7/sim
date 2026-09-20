const fields = [
  ['latitude_deg', 'Широта', '°', 6], ['longitude_deg', 'Долгота', '°', 6],
  ['altitude_msl_m', 'Высота MSL', ' м', 1], ['altitude_home_m', 'Над стартом', ' м', 1],
  ['airspeed_m_s', 'Воздушная AP', ' км/ч', 1, 3.6], ['groundspeed_m_s', 'Путевая', ' км/ч', 1, 3.6],
  ['climb_m_s', 'Набор высоты', ' м/с', 1], ['throttle_pct', 'Газ', '%', 0],
  ['gps_fix', 'GPS fix', '', 0], ['satellites', 'Спутники', '', 0], ['hdop', 'HDOP', '', 2],
  ['battery_voltage_v', 'Батарея', ' В', 2], ['battery_current_a', 'Ток', ' А', 1],
  ['battery_remaining_pct', 'Заряд', '%', 0],
];
export class TelemetryPanel {
  constructor(container) {
    this.rows = fields.map(([key, label, unit, digits, scale=1]) => {
      const row=document.createElement('div'), name=document.createElement('span'), value=document.createElement('b');
      name.textContent=label;value.textContent='—';row.append(name,value);container.append(row);
      return {key,unit,digits,scale,value};
    });
  }
  update(status) {
    for (const row of this.rows) {
      const value=status.connected ? status.telemetry?.[row.key] : null;
      row.value.textContent=Number.isFinite(value) ? (value*row.scale).toFixed(row.digits)+row.unit : '—';
    }
  }
}

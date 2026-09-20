export function aircraftBasis(heading, pitch, roll) {
  const forward = [
    Math.sin(heading) * Math.cos(pitch),
    Math.cos(heading) * Math.cos(pitch),
    Math.sin(pitch),
  ];
  const right = [Math.cos(heading), -Math.sin(heading), 0];
  const up = [
    -Math.sin(heading) * Math.sin(pitch),
    -Math.cos(heading) * Math.sin(pitch),
    Math.cos(pitch),
  ];
  return {
    forward,
    right: right.map((x, i) => x * Math.cos(roll) - up[i] * Math.sin(roll)),
    up: up.map((x, i) => x * Math.cos(roll) + right[i] * Math.sin(roll)),
  };
}

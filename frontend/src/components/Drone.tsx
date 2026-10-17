const ROTORS: [number, number][] = [
  [8.5, 8.5],
  [31.5, 8.5],
  [8.5, 31.5],
  [31.5, 31.5],
];

export function Drone() {
  return (
    <div className="drone" aria-hidden>
      <span className="drone-halo" />
      <svg className="drone-glyph" width="46" height="46" viewBox="0 0 40 40">
        {ROTORS.map(([x, y]) => (
          <line key={`a${x}${y}`} x1="20" y1="20" x2={x} y2={y} className="drone-arm" />
        ))}
        {ROTORS.map(([x, y]) => (
          <g key={`r${x}${y}`}>
            <circle cx={x} cy={y} r="6.5" className="drone-rotor" />
            <line x1={x - 4.2} y1={y} x2={x + 4.2} y2={y} className="drone-blade" />
            <circle cx={x} cy={y} r="1.3" className="drone-hub" />
          </g>
        ))}
        <rect x="14" y="12" width="12" height="16" rx="5.5" className="drone-body" />
        <circle cx="20" cy="15.6" r="2" className="drone-lens" />
        <line x1="17.2" y1="23" x2="22.8" y2="23" className="drone-seam" />
      </svg>
    </div>
  );
}

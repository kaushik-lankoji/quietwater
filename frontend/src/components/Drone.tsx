const PROPS: [number, number][] = [
  [9, 9],
  [31, 9],
  [9, 31],
  [31, 31],
];

export function Drone() {
  return (
    <div className="drone" aria-hidden>
      <span className="drone-halo" />
      <svg className="drone-glyph" width="44" height="44" viewBox="0 0 40 40">
        {PROPS.map(([x, y]) => (
          <line key={`a${x}${y}`} x1="20" y1="20" x2={x} y2={y} className="drone-arm" />
        ))}
        {PROPS.map(([x, y]) => (
          <circle key={`p${x}${y}`} cx={x} cy={y} r="6" className="drone-prop" />
        ))}
        <circle cx="20" cy="20" r="10" className="drone-body" />
        <circle cx="16.2" cy="18.6" r="2.6" className="drone-eye" />
        <circle cx="23.8" cy="18.6" r="2.6" className="drone-eye" />
        <circle cx="16.8" cy="18.9" r="1.1" className="drone-pupil" />
        <circle cx="24.4" cy="18.9" r="1.1" className="drone-pupil" />
        <path d="M18 23.6q2 1.6 4 0" className="drone-smile" />
      </svg>
    </div>
  );
}

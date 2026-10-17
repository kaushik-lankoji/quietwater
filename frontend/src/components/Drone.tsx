export function Drone() {
  return (
    <div className="drone" aria-hidden>
      <span className="drone-halo" />
      <svg className="drone-glyph" width="40" height="40" viewBox="0 0 40 40">
        <line x1="20" y1="2" x2="20" y2="7" className="drone-heading" />
        <path d="M20 8c2.6 0 4 2.2 4 5v13.5c0 1.8-1.4 3.5-4 3.5s-4-1.7-4-3.5V13c0-2.8 1.4-5 4-5z" className="drone-body" />
        <path d="M16 26.5l-4.5 4h4.5zM24 26.5l4.5 4H24z" className="drone-body" />
        <path d="M17.5 32.5h5" className="drone-prop" />
        <circle cx="20" cy="13.5" r="1.4" className="drone-eye" />
      </svg>
    </div>
  );
}

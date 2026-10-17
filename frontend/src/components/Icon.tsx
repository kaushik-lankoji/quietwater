const PATHS: Record<string, string> = {
  play: "M7 4.5v15l12-7.5z",
  pause: "M7 4h3.5v16H7zM13.5 4H17v16h-3.5z",
  replay: "M12 5V2L7 6l5 4V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7z",
  check: "M5 12.5 10 17 19 7",
  x: "M6 6l12 12M18 6 6 18",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zm10-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  download: "M12 3v12m0 0 5-5m-5 5-5-5M4 19h16",
  chevronDown: "M6 9l6 6 6-6",
  chevronLeft: "M15 6l-6 6 6 6",
  chevronRight: "M9 6l6 6-6 6",
  up: "M12 19V5m0 0-6 6m6-6 6 6",
  down: "M12 5v14m0 0-6-6m6 6 6-6",
  send: "M3 11.5 21 3l-8.5 18-2-7.5z",
  copy: "M8 8h11v13H8zM5 16H4V3h11v1",
  alert: "M12 3 2 21h20L12 3zm0 6v5m0 3v.5",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 4v5l3 2",
  dot: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  undo: "M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  sliders: "M4 6h10m4 0h2M4 12h4m4 0h8M4 18h12m4 0h0M14 4v4M8 10v4M16 16v4",
  file: "M6 2h8l5 5v15H6zM14 2v5h5",
  wave: "M2 12c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3M2 17c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3",
  close: "M6 6l12 12M18 6 6 18",
  minus: "M5 12h14",
};

const FILLED = new Set(["play", "pause", "replay", "dot", "send"]);

export function Icon({ name, size = 18, title }: { name: keyof typeof PATHS | string; size?: number; title?: string }) {
  const d = PATHS[name] ?? PATHS.dot;
  const filled = FILLED.has(name);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      className="icon"
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {title && <title>{title}</title>}
      <path d={d} />
    </svg>
  );
}

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="logo">
      <circle cx="16" cy="16" r="3.5" fill="var(--accent)" />
      <circle cx="16" cy="16" r="8" fill="none" stroke="var(--accent)" strokeOpacity=".6" strokeWidth="2" />
      <circle cx="16" cy="16" r="12.5" fill="none" stroke="var(--accent)" strokeOpacity=".25" strokeWidth="2" />
    </svg>
  );
}

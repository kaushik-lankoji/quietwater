const PATHS = {
  play: "M8 5.5v13l10.5-6.5z",
  pause: "M8.5 5v14M15.5 5v14",
  replay: "M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4.5v3.6h3.6",
  flood: "M3 9c1.5 0 1.5-1.5 3-1.5S7.5 9 9 9s1.5-1.5 3-1.5S13.5 9 15 9s1.5-1.5 3-1.5S19.5 9 21 9M3 13c1.5 0 1.5-1.5 3-1.5s1.5 1.5 3 1.5 1.5-1.5 3-1.5 1.5 1.5 3 1.5 1.5-1.5 3-1.5 1.5 1.5 3 1.5M3 17c1.5 0 1.5-1.5 3-1.5s1.5 1.5 3 1.5 1.5-1.5 3-1.5 1.5 1.5 3 1.5 1.5-1.5 3-1.5 1.5 1.5 3 1.5",
  receipt: "M6 3.5h12v17l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3zM9 8h6M9 11.5h6M9 15h3.5",
  plus: "M12 5v14M5 12h14",
  check: "M5.5 12.5l4 4 9-9",
  x: "M7 7l10 10M17 7 7 17",
  minus: "M6 12h12",
  close: "M7 7l10 10M17 7 7 17",
  chevronDown: "M7 10l5 5 5-5",
  chevronLeft: "M14 7l-5 5 5 5",
  chevronRight: "M10 7l5 5-5 5",
  up: "M12 18V6M7 11l5-5 5 5",
  down: "M12 6v12M7 13l5 5 5-5",
  download: "M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14",
  send: "M4 12 20 4l-4 16-4-6.5zM12 13.5 20 4",
  copy: "M9 9h10v11H9zM5 15V4h10",
  alert: "M12 4 3 19.5h18zM12 10v4.5M12 17v.01",
  file: "M7 3.5h7l4 4V20.5H7zM14 3.5v4h4",
  undo: "M9 14.5 4.5 10 9 5.5M4.5 10H15a4.5 4.5 0 0 1 0 9h-3",
  wave: "M3 12c2.2 0 2.2-2.5 4.5-2.5S9.8 12 12 12s2.2-2.5 4.5-2.5S18.8 12 21 12",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, title }: { name: IconName; size?: number; title?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      className="icon"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {title && <title>{title}</title>}
      <path d={PATHS[name]} />
    </svg>
  );
}

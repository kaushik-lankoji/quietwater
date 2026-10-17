import type { Point, Rung, Shape } from "./types";

export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function mmss(seconds: number): string {
  const s = Math.max(0, Math.round(Math.abs(seconds)));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function latlon([x, y]: Point, origin: { lat: number; lon: number }): string {
  const lat = origin.lat - y / 111_320;
  const lon = origin.lon + x / (111_320 * Math.cos((origin.lat * Math.PI) / 180));
  return `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? "N" : "S"} ${Math.abs(lon).toFixed(4)}°${lon < 0 ? "W" : "E"}`;
}

export const rungVar = (r: Rung) => `var(--${r.toLowerCase()})`;

export function nearestPoint(p: Point, s: Shape): Point {
  if (s.type === "rect") {
    return [Math.min(Math.max(p[0], s.x!), s.x! + s.w!), Math.min(Math.max(p[1], s.y!), s.y! + s.h!)];
  }
  if (s.type === "circle") {
    const dx = p[0] - s.x!;
    const dy = p[1] - s.y!;
    const d = Math.hypot(dx, dy);
    if (d <= s.r! || d === 0) return p;
    return [s.x! + (dx * s.r!) / d, s.y! + (dy * s.r!) / d];
  }
  const pts = s.points ?? [];
  let best: Point = pts[0];
  let bestD = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i];
    const [bx, by] = pts[i + 1];
    const dx = bx - ax;
    const dy = by - ay;
    const len = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / len));
    const q: Point = [ax + t * dx, ay + t * dy];
    const d = Math.hypot(p[0] - q[0], p[1] - q[1]);
    if (d < bestD) {
      bestD = d;
      best = q;
    }
  }
  return best;
}

export function stepLabel(step: string): string {
  return (
    {
      S0: "Is it a vehicle?",
      S1: "Identity",
      S2: "Hail",
      S3: "Consistency",
      S4: "Behavior",
      S5: "Confidence × consequence",
      M1: "Match lost vehicle",
      M2: "Re-scan",
      M3: "Drift + hand to owner",
    }[step] ?? step
  );
}

export function display(value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function cls(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(" ");
}

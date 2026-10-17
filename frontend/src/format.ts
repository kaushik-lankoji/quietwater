import type { Point } from "./types";

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

export function display(value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function cls(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(" ");
}

import type { Rung, Urgency } from "../types";
import { CONTACT_RADIUS_MAX, CONTACT_RADIUS_MIN, DRONE_POSITION, RANGE_M } from "./constants";

export type Tier = "low" | "mid" | "high";

export const TIER_LABEL: Record<Tier, string> = { low: "Low", mid: "Medium", high: "High" };

export function tierOf(rung: Rung, urgency?: Urgency): Tier {
  if (urgency === "urgent" || rung === "R4" || rung === "R5") return "high";
  if (rung === "R2" || rung === "R3") return "mid";
  return "low";
}

export interface Polar {
  distance: number;
  bearing: number;
  dx: number;
  dy: number;
}

export function toPolar(x: number, y: number): Polar {
  const dx = x - DRONE_POSITION.x;
  const dy = y - DRONE_POSITION.y;
  const bearing = ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360;
  return { distance: Math.hypot(dx, dy), bearing, dx, dy };
}

export const inRange = (p: Polar, rangeM = RANGE_M) => p.distance <= rangeM;

export function contactRadius(sizeM: number): number {
  const t = Math.max(0, Math.min(1, (sizeM - 0.3) / 2.7));
  return CONTACT_RADIUS_MIN + t * (CONTACT_RADIUS_MAX - CONTACT_RADIUS_MIN);
}

export function formatBearing(deg: number): string {
  return `${String(Math.round(deg) % 360).padStart(3, "0")}°`;
}

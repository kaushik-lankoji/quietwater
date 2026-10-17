import type { Contact } from "../types";
import {
  ECHO_FADE_IN_MS,
  ECHO_FADE_OUT_MS,
  ECHO_STALE_GRACE_MS,
  ECHO_STALE_OPACITY,
  HIT_CELL_PX,
  HIT_TOLERANCE_PX,
  HOVER_SCALE,
  PULSE_ECHOES,
  PULSE_OPACITY,
  PULSE_PERIOD_MS,
  PULSE_TRAVEL_MS,
  RANGE_M,
  RING_COUNT,
  RING_RADIUS_FRACTION,
  RIPPLE_PERIOD_MS,
  RIPPLE_SPREAD_PX,
} from "./constants";
import { contactRadius, inRange, tierOf, toPolar, type Tier } from "./geometry";

interface Live {
  contact: Contact;
  dx: number;
  dy: number;
  distance: number;
  inRange: boolean;
}

export interface Echo {
  id: string;
  contact: Contact;
  dx: number;
  dy: number;
  radius: number;
  tier: Tier;
  pingedAt: number;
  leftAt: number | null;
}

interface Palette {
  low: string;
  mid: string;
  high: string;
  pulse: string;
  ring: string;
  label: string;
  ink: string;
  surface: string;
  font: string;
}

const TIER_ORDER: Record<Tier, number> = { low: 0, mid: 1, high: 2 };

function readPalette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    low: v("--risk-low"),
    mid: v("--risk-mid"),
    high: v("--risk-high"),
    pulse: v("--pulse-green"),
    ring: v("--divider"),
    label: v("--text-tertiary"),
    ink: v("--text-primary"),
    surface: v("--surface"),
    font: v("--font"),
  };
}

function withAlpha(color: string, alpha: number): string {
  const hex = color.replace("#", "");
  if (hex.length !== 6) return color;
  const n = parseInt(hex, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function blend(a: string, b: string, t: number): string {
  const x = parseInt(a.replace("#", ""), 16);
  const y = parseInt(b.replace("#", ""), 16);
  const mix = (s: number) => Math.round(((x >> s) & 255) * (1 - t) + ((y >> s) & 255) * t);
  return `#${((mix(16) << 16) | (mix(8) << 8) | mix(0)).toString(16).padStart(6, "0")}`;
}

export class RadarEngine {
  private ctx: CanvasRenderingContext2D;
  private palette: Palette;
  private live = new Map<string, Live>();
  private echoes = new Map<string, Echo>();
  private grid = new Map<number, Echo[]>();
  private gridDirty = true;
  private width = 0;
  private height = 0;
  private dpr = 1;
  private epoch = performance.now();
  private lastPulse = -1;
  private lastFront = 0;
  private frame = 0;
  private reduced: boolean;
  hovered: string | null = null;
  selected: string | null = null;
  /** Contacts whose hand-off the operator has dealt with: drawn as a grayed-out red. */
  handled: ReadonlySet<string> = new Set();
  onChange: (() => void) | null = null;

  constructor(private canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext("2d")!;
    this.palette = readPalette();
    this.reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  }

  start() {
    const loop = (t: number) => {
      this.draw(t);
      this.frame = requestAnimationFrame(loop);
    };
    this.frame = requestAnimationFrame(loop);
  }

  stop() {
    cancelAnimationFrame(this.frame);
  }

  resize(width: number, height: number) {
    this.dpr = window.devicePixelRatio || 1;
    this.width = width;
    this.height = height;
    this.canvas.width = Math.round(width * this.dpr);
    this.canvas.height = Math.round(height * this.dpr);
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    this.gridDirty = true;
  }

  reset() {
    this.echoes.clear();
    this.epoch = performance.now();
    this.lastPulse = -1;
    this.lastFront = 0;
    this.gridDirty = true;
    this.onChange?.();
  }

  setContacts(contacts: Contact[]) {
    const next = new Map<string, Live>();
    for (const c of contacts) {
      const p = toPolar(c.x, c.y);
      next.set(c.id, { contact: c, dx: p.dx, dy: p.dy, distance: p.distance, inRange: inRange(p) });
      const echo = this.echoes.get(c.id);
      if (echo) {
        echo.contact = c;
        if (!inRange(p) && echo.leftAt === null) echo.leftAt = performance.now();
      }
    }
    this.live = next;
  }

  get ringRadius() {
    return Math.min(this.width, this.height) * RING_RADIUS_FRACTION;
  }

  private get scale() {
    return this.ringRadius / RANGE_M;
  }

  private get maxFront() {
    return Math.hypot(this.width / 2, this.height / 2) + 40;
  }

  position(echo: Echo): { x: number; y: number } {
    return { x: this.width / 2 + echo.dx * this.scale, y: this.height / 2 + echo.dy * this.scale };
  }

  echo(id: string): Echo | undefined {
    return this.echoes.get(id);
  }

  private sweep(lo: number, hi: number, now: number) {
    const k = this.scale;
    let changed = false;
    for (const l of this.live.values()) {
      if (!l.inRange) continue;
      const r = l.distance * k;
      if (r < lo || r >= hi) continue;
      this.echoes.set(l.contact.id, {
        id: l.contact.id,
        contact: l.contact,
        dx: l.dx,
        dy: l.dy,
        radius: contactRadius(l.contact.size_m),
        tier: tierOf(l.contact.rung, l.contact.urgency),
        pingedAt: now,
        leftAt: null,
      });
      changed = true;
    }
    if (changed) {
      this.gridDirty = true;
      this.onChange?.();
    }
  }

  private advancePulse(now: number): { front: number; progress: number } | null {
    const elapsed = now - this.epoch;
    const index = Math.floor(elapsed / PULSE_PERIOD_MS);
    const local = elapsed - index * PULSE_PERIOD_MS;
    const max = this.maxFront;
    if (index !== this.lastPulse) {
      if (this.lastPulse >= 0 && this.lastFront < max) this.sweep(this.lastFront, max, now);
      this.lastPulse = index;
      this.lastFront = 0;
    }
    if (local >= PULSE_TRAVEL_MS) {
      if (this.lastFront < max) this.sweep(this.lastFront, max, now);
      this.lastFront = max;
      return null;
    }
    const progress = local / PULSE_TRAVEL_MS;
    const front = progress * max;
    this.sweep(this.lastFront, front, now);
    this.lastFront = front;
    return { front, progress };
  }

  private alpha(echo: Echo, now: number): number {
    const age = now - echo.pingedAt;
    let a = Math.min(1, age / ECHO_FADE_IN_MS);
    const stale = age - PULSE_PERIOD_MS - ECHO_STALE_GRACE_MS;
    if (stale > 0) a *= Math.max(ECHO_STALE_OPACITY, 1 - (stale / 300) * (1 - ECHO_STALE_OPACITY));
    const gone = age - 2 * PULSE_PERIOD_MS - ECHO_STALE_GRACE_MS;
    if (gone > 0) a *= Math.max(0, 1 - gone / ECHO_FADE_OUT_MS);
    if (echo.leftAt !== null) a *= Math.max(0, 1 - (now - echo.leftAt) / ECHO_FADE_OUT_MS);
    return a;
  }

  private prune(now: number) {
    let removed = false;
    for (const [id, e] of this.echoes) {
      const age = now - e.pingedAt;
      const expired = age > 2 * PULSE_PERIOD_MS + ECHO_STALE_GRACE_MS + ECHO_FADE_OUT_MS;
      const left = e.leftAt !== null && now - e.leftAt > ECHO_FADE_OUT_MS;
      if (expired || left) {
        this.echoes.delete(id);
        removed = true;
      }
    }
    if (removed) {
      this.gridDirty = true;
      this.onChange?.();
    }
  }

  private draw(now: number) {
    const { ctx, width: w, height: h, palette: p } = this;
    if (!w || !h) return;
    const pulse = this.advancePulse(now);
    this.prune(now);
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;
    const cy = h / 2;

    ctx.lineWidth = 1;
    ctx.strokeStyle = p.ring;
    ctx.beginPath();
    ctx.moveTo(0, cy + 0.5);
    ctx.lineTo(w, cy + 0.5);
    ctx.moveTo(cx + 0.5, 0);
    ctx.lineTo(cx + 0.5, h);
    ctx.stroke();

    const R = this.ringRadius;
    ctx.font = `500 11px ${p.font}`;
    ctx.fillStyle = p.label;
    ctx.textBaseline = "bottom";
    for (let i = 1; i <= RING_COUNT; i++) {
      const r = (R * i) / RING_COUNT;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      const a = -Math.PI / 4;
      ctx.fillText(`${Math.round((RANGE_M * i) / RING_COUNT)} m`, cx + Math.cos(a) * r + 6, cy + Math.sin(a) * r - 4);
    }

    if (pulse) {
      const fade = PULSE_OPACITY * (1 - pulse.progress);
      if (!this.reduced && pulse.front > 48) {
        const band = ctx.createRadialGradient(cx, cy, Math.max(0, pulse.front - 48), cx, cy, pulse.front);
        band.addColorStop(0, withAlpha(p.pulse, 0));
        band.addColorStop(1, withAlpha(p.pulse, fade * 0.16));
        ctx.fillStyle = band;
        ctx.beginPath();
        ctx.arc(cx, cy, pulse.front, 0, Math.PI * 2);
        ctx.fill();
      }
      const echoes = this.reduced ? [0] : PULSE_ECHOES;
      echoes.forEach((offset, i) => {
        const r = pulse.front - offset;
        if (r <= 0) return;
        ctx.strokeStyle = withAlpha(p.pulse, fade / (1 + i * 1.6));
        ctx.lineWidth = i === 0 ? 2 : 1.5;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
      });
    }

    const list = [...this.echoes.values()].sort((a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier]);
    for (const e of list) {
      const a = this.alpha(e, now);
      if (a <= 0.01) continue;
      const { x, y } = this.position(e);
      const done = e.tier === "high" && this.handled.has(e.id);
      const color = done ? blend(p.high, p.low, 0.62) : p[e.tier];
      const hover = e.id === this.hovered;
      const r = e.radius * (hover ? HOVER_SCALE : 1);

      if (e.tier === "high" && !done && !this.reduced) {
        const phase = ((now - e.pingedAt) % RIPPLE_PERIOD_MS) / RIPPLE_PERIOD_MS;
        ctx.strokeStyle = withAlpha(color, 0.45 * (1 - phase) * a);
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(x, y, r + 2 + phase * RIPPLE_SPREAD_PX, 0, Math.PI * 2);
        ctx.stroke();
      }

      if (hover) {
        ctx.save();
        ctx.shadowColor = withAlpha(p.ink, 0.18);
        ctx.shadowBlur = 16;
        ctx.fillStyle = p.surface;
        ctx.beginPath();
        ctx.arc(x, y, r + 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }

      ctx.fillStyle = withAlpha(color, 0.18 * a);
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = withAlpha(color, a);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();

      if (e.id === this.selected) {
        ctx.strokeStyle = withAlpha(p.ink, 0.8 * a);
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(x, y, r + 8, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  private cellKey(cx: number, cy: number) {
    return cx * 100003 + cy;
  }

  private rebuildGrid() {
    this.grid.clear();
    for (const e of this.echoes.values()) {
      const { x, y } = this.position(e);
      const key = this.cellKey(Math.floor(x / HIT_CELL_PX), Math.floor(y / HIT_CELL_PX));
      const cell = this.grid.get(key);
      if (cell) cell.push(e);
      else this.grid.set(key, [e]);
    }
    this.gridDirty = false;
  }

  hitTest(px: number, py: number): Echo | null {
    if (this.gridDirty) this.rebuildGrid();
    const now = performance.now();
    const reach = Math.ceil((HIT_TOLERANCE_PX + 14) / HIT_CELL_PX);
    const gx = Math.floor(px / HIT_CELL_PX);
    const gy = Math.floor(py / HIT_CELL_PX);
    let best: Echo | null = null;
    let bestD = Infinity;
    for (let i = gx - reach; i <= gx + reach; i++) {
      for (let j = gy - reach; j <= gy + reach; j++) {
        const cell = this.grid.get(this.cellKey(i, j));
        if (!cell) continue;
        for (const e of cell) {
          if (this.alpha(e, now) < 0.2) continue;
          const { x, y } = this.position(e);
          const d = Math.hypot(px - x, py - y);
          if (d <= e.radius + HIT_TOLERANCE_PX && d < bestD) {
            best = e;
            bestD = d;
          }
        }
      }
    }
    return best;
  }
}

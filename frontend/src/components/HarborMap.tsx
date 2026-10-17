import { memo, useMemo, useRef, useState, type ReactNode, type SVGProps } from "react";
import { cls, nearestPoint, pct, rungVar } from "../format";
import type { Asset, AssetRef, Contact, Harbor, Point, RulesData, Shape, Zone } from "../types";
import { RungChip } from "./bits";

const VIEW = { x: 150, y: 140, w: 1850, h: 1180 };

export interface Layers {
  zones: boolean;
  trails: boolean;
  labels: boolean;
}

interface Props {
  harbor: Harbor;
  rules: RulesData;
  contacts?: Contact[];
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  focus?: { contactId: string; asset: AssetRef | null } | null;
  highlight?: Set<string>;
  layers?: Layers;
  compact?: boolean;
  children?: ReactNode;
}

function ShapeEl({ shape, ...rest }: { shape: Shape } & SVGProps<SVGElement>) {
  const props = rest as Record<string, unknown>;
  if (shape.type === "rect") return <rect x={shape.x} y={shape.y} width={shape.w} height={shape.h} rx={6} {...props} />;
  if (shape.type === "circle") return <circle cx={shape.x} cy={shape.y} r={shape.r} {...props} />;
  const pts = (shape.points ?? []).map((p) => p.join(",")).join(" ");
  return <polyline points={pts} fill="none" strokeLinejoin="round" strokeLinecap="round" {...props} />;
}

function anchor(shape: Shape): Point {
  if (shape.type === "rect") return [shape.x! + shape.w! / 2, shape.y! + shape.h! / 2];
  if (shape.type === "circle") return [shape.x!, shape.y!];
  const pts = shape.points ?? [[0, 0]];
  return pts[Math.floor(pts.length / 2)];
}

const Land = memo(function Land({ harbor }: { harbor: Harbor }) {
  const { w } = harbor.bounds;
  return (
    <g>
      <rect x={-3000} y={-3000} width={w + 6000} height={3000} fill="var(--land)" />
      <rect x={-3000} y={0} width={3000} height={1250} fill="var(--land)" />
      <rect x={w} y={0} width={3000} height={1170} fill="var(--land)" />
      {harbor.land.map((poly, i) => (
        <polygon
          key={i}
          points={poly.map((p) => p.join(",")).join(" ")}
          fill="var(--land)"
          stroke="var(--land-edge)"
          strokeWidth={2}
          strokeLinejoin="round"
        />
      ))}
      {harbor.piers.map((p) => (
        <g key={p.name}>
          <rect x={p.x} y={p.y} width={p.w} height={p.h} fill="var(--pier)" stroke="var(--land-edge)" strokeWidth={2} />
          <text
            x={p.x + p.w / 2}
            y={p.y + p.h - 16}
            textAnchor="middle"
            fontSize={21}
            fontWeight={700}
            fill="var(--map-label)"
            transform={`rotate(-90 ${p.x + p.w / 2} ${p.y + p.h - 16})`}
            dy={5}
            dx={0}
            style={{ letterSpacing: "0.08em" }}
          >
            {p.name.toUpperCase()}
          </text>
        </g>
      ))}
      {harbor.labels.map((l) => (
        <text
          key={l.text}
          x={l.x}
          y={l.y}
          textAnchor="middle"
          fontSize={28}
          fontWeight={650}
          fill="var(--map-label)"
          transform={l.rotate ? `rotate(${l.rotate} ${l.x} ${l.y})` : undefined}
          style={{ letterSpacing: "0.14em", textTransform: "uppercase" }}
        >
          {l.text}
        </text>
      ))}
    </g>
  );
});

function Grid({ harbor }: { harbor: Harbor }) {
  const lines = [];
  for (let x = 200; x < harbor.bounds.w; x += 200) lines.push(<line key={`x${x}`} x1={x} y1={0} x2={x} y2={harbor.bounds.h} />);
  for (let y = 200; y < harbor.bounds.h; y += 200) lines.push(<line key={`y${y}`} x1={0} y1={y} x2={harbor.bounds.w} y2={y} />);
  return (
    <g stroke="var(--grid)" strokeWidth={1.5}>
      {lines}
    </g>
  );
}

function ZoneEl({ zone, harbor, highlight }: { zone: Zone; harbor: Harbor; highlight: boolean }) {
  const s = zone.shape;
  if (s.type === "rect" && s.w! * s.h! > harbor.bounds.w * harbor.bounds.h * 0.45) return null;
  const crit = zone.critical;
  const stroke = highlight ? "var(--accent)" : crit ? "var(--zone-crit)" : "var(--zone)";
  const common = {
    stroke,
    strokeWidth: highlight ? 4 : 2,
    strokeDasharray: crit ? "12 8" : "5 9",
  };
  let label: Point;
  let anchorText: "start" | "middle" = "start";
  if (s.type === "rect") label = [s.x! + 12, s.y! + 30];
  else if (s.type === "circle") {
    label = [s.x!, s.y! - s.r! - 10];
    anchorText = "middle";
  } else {
    const pts = s.points ?? [[0, 0]];
    const at = pts[Math.min(2, pts.length - 1)];
    label = [at[0] + 14, at[1] - (s.width ?? 0) / 2 - 12];
  }
  return (
    <g>
      {s.type === "line" ? (
        <ShapeEl shape={s} strokeWidth={s.width} stroke={crit ? "var(--zone-crit-fill)" : "transparent"} />
      ) : (
        <ShapeEl shape={s} fill={crit ? "url(#hatch)" : highlight ? "var(--accent-soft)" : "none"} {...common} />
      )}
      {s.type !== "line" ? null : <ShapeEl shape={{ ...s }} {...common} strokeWidth={1.5} opacity={0.6} />}
      <text
        x={label[0]}
        y={label[1]}
        textAnchor={anchorText}
        fontSize={21}
        fontWeight={750}
        fill={highlight ? "var(--accent)" : crit ? "var(--zone-crit)" : "var(--map-label)"}
        style={{ letterSpacing: "0.1em" }}
      >
        {zone.name.toUpperCase()}
        {crit ? " · CRITICAL" : ""}
      </text>
    </g>
  );
}

function AssetEl({ asset, highlight, focus }: { asset: Asset; highlight: boolean; focus: boolean }) {
  const s = asset.shape;
  const off = !asset.active;
  const [ax, ay] = anchor(s);
  const ring = focus ? "var(--r5)" : highlight ? "var(--accent)" : null;
  let body: ReactNode;
  let labelAt: Point = [ax, ay];
  if (asset.kind === "ship") {
    const rx = Math.min(s.w ?? 0, s.h ?? 0) * 0.45;
    body = (
      <rect x={s.x} y={s.y} width={s.w} height={s.h} rx={rx} fill="var(--vessel)" fillOpacity={0.88} stroke="var(--land-edge)" strokeWidth={2} />
    );
    labelAt = (s.h ?? 0) > (s.w ?? 0) ? [s.x! + s.w! + 14, s.y! + 30] : [s.x! + 8, s.y! + s.h! + 30];
  } else if (asset.kind === "fuel_dock") {
    body = (
      <g>
        <rect
          x={s.x}
          y={s.y}
          width={s.w}
          height={s.h}
          rx={6}
          fill="var(--r3)"
          fillOpacity={off ? 0.06 : 0.22}
          stroke={off ? "var(--muted)" : "var(--r3)"}
          strokeWidth={2.5}
          strokeDasharray={off ? "6 6" : undefined}
        />
        <path
          d={`M${ax} ${ay - 18} C ${ax + 13} ${ay - 3} ${ax + 13} ${ay + 13} ${ax} ${ay + 13} C ${ax - 13} ${ay + 13} ${ax - 13} ${ay - 3} ${ax} ${ay - 18} Z`}
          fill={off ? "var(--muted)" : "var(--r3)"}
        />
      </g>
    );
    labelAt = [s.x!, s.y! + s.h! + 30];
  } else if (asset.kind === "dive_area") {
    body = (
      <g>
        <ShapeEl shape={s} fill="var(--r5)" fillOpacity={off ? 0.02 : 0.08} stroke="var(--r5)" strokeWidth={2} strokeDasharray="4 6" />
        <rect x={ax - 21} y={ay - 15} width={42} height={30} rx={3} fill="#e5283c" />
        <path d={`M${ax - 21} ${ay - 15} L ${ax + 21} ${ay + 15}`} stroke="#fff" strokeWidth={7} />
      </g>
    );
    labelAt = [ax, ay + (s.r ?? 0) + 32];
  } else if (asset.kind === "cable") {
    body = (
      <g>
        <ShapeEl shape={s} stroke="var(--cable)" strokeOpacity={0.18} strokeWidth={(s.width ?? 10) + 14} />
        <ShapeEl shape={s} stroke="var(--cable)" strokeWidth={4} strokeDasharray="18 10" opacity={off ? 0.4 : 1} />
      </g>
    );
    const pts = s.points ?? [];
    labelAt = pts.length > 2 ? [pts[2][0] - 140, pts[2][1] + 34] : [ax, ay + 30];
  } else {
    body = <ShapeEl shape={s} fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth={2} />;
  }
  return (
    <g opacity={off ? 0.75 : 1}>
      {ring && (
        <ShapeEl
          shape={s}
          fill="none"
          stroke={ring}
          strokeWidth={s.type === "line" ? (s.width ?? 10) + 22 : 10}
          strokeOpacity={0.35}
        />
      )}
      {body}
      <text
        x={labelAt[0]}
        y={labelAt[1]}
        textAnchor={asset.kind === "dive_area" ? "middle" : "start"}
        fontSize={23}
        fontWeight={650}
        fill="var(--map-label)"
      >
        {asset.name}
        {off ? " (inactive)" : ""}
      </text>
    </g>
  );
}

function Vessels({ rules }: { rules: RulesData }) {
  return (
    <g>
      {rules.traffic.map((v) => (
        <g key={v.id} transform={`translate(${v.x} ${v.y})`}>
          <path d="M0 -22 L11 -6 L11 19 L-11 19 L-11 -6 Z" fill="var(--vessel)" stroke="var(--water)" strokeWidth={2.5} />
          <text x={18} y={7} fontSize={21} fontWeight={650} fill="var(--map-label)">
            {v.name}
          </text>
        </g>
      ))}
    </g>
  );
}

function radius(c: Contact) {
  if (c.rung === "R0") return ["biologic", "debris"].includes(c.label) ? 7 : 10;
  if (c.rung === "R4" || c.rung === "R5") return 15;
  return 12;
}

const ContactGlyph = memo(function ContactGlyph({
  c,
  selected,
  showLabel,
  onSelect,
  onHover,
}: {
  c: Contact;
  selected: boolean;
  showLabel: boolean;
  onSelect?: (id: string) => void;
  onHover: (c: Contact | null) => void;
}) {
  const r = radius(c);
  const color = rungVar(c.rung);
  const quiet = c.rung === "R0" && ["biologic", "debris"].includes(c.label);
  return (
    <g
      className={cls("contact", c.requires_human && "pulse", selected && "selected")}
      style={{ transform: `translate(${c.x}px, ${c.y}px)` }}
      onClick={(e) => {
        e.stopPropagation();
        onSelect?.(c.id);
      }}
      onMouseEnter={() => onHover(c)}
      onMouseLeave={() => onHover(null)}
      role="button"
      tabIndex={-1}
      aria-label={`${c.id} ${c.label_text} ${c.rung}`}
    >
      <circle className="hit" r={30} />
      {c.requires_human && <circle className="ring" r={r + 6} stroke={color} />}
      {selected && <circle className="sel" r={r + 12} />}
      {!quiet && (
        <line
          x1={0}
          y1={0}
          x2={0}
          y2={-(r + 16)}
          stroke={color}
          strokeWidth={4.5}
          strokeLinecap="round"
          transform={`rotate(${c.heading})`}
        />
      )}
      <circle r={r} fill={color} fillOpacity={quiet ? 0.55 : 1} stroke="var(--water)" strokeWidth={3} />
      {showLabel && (
        <text
          x={r + 10}
          y={-r - 6}
          fontSize={25}
          fontWeight={750}
          fill="var(--text)"
          stroke="var(--water)"
          strokeWidth={7}
          paintOrder="stroke"
          style={{ fontFamily: "var(--mono)" }}
        >
          {c.id}
        </text>
      )}
    </g>
  );
});

export function HarborMap({
  harbor,
  rules,
  contacts = [],
  selected = null,
  onSelect,
  focus,
  highlight,
  layers = { zones: true, trails: true, labels: true },
  compact,
  children,
}: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ c: Contact; x: number; y: number } | null>(null);
  const mouse = useRef<[number, number]>([0, 0]);
  const focusContact = focus ? contacts.find((c) => c.id === focus.contactId) : undefined;
  const focusAsset = focus?.asset ? rules.assets.find((a) => a.id === focus.asset!.id) : undefined;
  const focusLine = useMemo(() => {
    if (!focusContact || !focusAsset) return null;
    const p: Point = [focusContact.x, focusContact.y];
    return { from: p, to: nearestPoint(p, focusAsset.shape) };
  }, [focusContact, focusAsset]);

  const crowded = contacts.length > 60;
  const sortedContacts = useMemo(
    () => [...contacts].sort((a, b) => a.rung.localeCompare(b.rung) || Number(a.requires_human) - Number(b.requires_human)),
    [contacts],
  );

  return (
    <div
      className={cls("map-panel", !compact && "panel")}
      ref={wrap}
      onMouseMove={(e) => {
        const rect = wrap.current?.getBoundingClientRect();
        if (rect) mouse.current = [e.clientX - rect.left, e.clientY - rect.top];
      }}
      style={compact ? { borderRadius: 10, border: "1px solid var(--border)", height: 280 } : undefined}
    >
      <svg
        className="map-svg"
        viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`}
        preserveAspectRatio="xMidYMid meet"
        onClick={() => onSelect?.(null)}
        role="img"
        aria-label="Harbor map"
      >
        <defs>
          <pattern id="hatch" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="14" height="14" fill="var(--zone-crit-fill)" />
            <line x1="0" y1="0" x2="0" y2="14" stroke="var(--zone-crit)" strokeOpacity="0.16" strokeWidth="4" />
          </pattern>
          <radialGradient id="waterGlow" cx="50%" cy="60%" r="70%">
            <stop offset="0%" stopColor="var(--water-2)" />
            <stop offset="100%" stopColor="var(--water)" />
          </radialGradient>
        </defs>
        <rect x={-3000} y={-3000} width={8000} height={8000} fill="url(#waterGlow)" />
        <Grid harbor={harbor} />
        <Land harbor={harbor} />
        {layers.zones && rules.zones.map((z) => <ZoneEl key={z.id} zone={z} harbor={harbor} highlight={!!highlight?.has(z.id)} />)}
        {rules.assets.map((a) => (
          <AssetEl key={a.id} asset={a} highlight={!!highlight?.has(a.id)} focus={a.id === focusAsset?.id} />
        ))}
        <Vessels rules={rules} />
        {!compact && (
          <g transform={`translate(${VIEW.x + 40} ${VIEW.y + VIEW.h - 40})`}>
            <line x1={0} y1={0} x2={200} y2={0} stroke="var(--map-label)" strokeWidth={3} />
            <line x1={0} y1={-8} x2={0} y2={8} stroke="var(--map-label)" strokeWidth={3} />
            <line x1={200} y1={-8} x2={200} y2={8} stroke="var(--map-label)" strokeWidth={3} />
            <text x={100} y={-14} textAnchor="middle" fontSize={21} fontWeight={700} fill="var(--map-label)">
              200 m
            </text>
          </g>
        )}
        {layers.trails &&
          contacts.map((c) =>
            c.trail.length > 1 && !(c.rung === "R0" && ["biologic", "debris"].includes(c.label)) ? (
              <polyline
                key={`t-${c.id}`}
                points={[...c.trail, [c.x, c.y]].map((p) => p.join(",")).join(" ")}
                fill="none"
                stroke={rungVar(c.rung)}
                strokeOpacity={0.45}
                strokeWidth={3.5}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ) : null,
          )}
        {focusLine && (
          <g>
            <line
              x1={focusLine.from[0]}
              y1={focusLine.from[1]}
              x2={focusLine.to[0]}
              y2={focusLine.to[1]}
              stroke="var(--r5)"
              strokeWidth={4}
              strokeDasharray="12 8"
            />
            <text
              x={(focusLine.from[0] + focusLine.to[0]) / 2 + 10}
              y={(focusLine.from[1] + focusLine.to[1]) / 2}
              fontSize={25}
              fontWeight={800}
              fill="var(--r5)"
              stroke="var(--water)"
              strokeWidth={7}
              paintOrder="stroke"
            >
              {focus?.asset?.distance_m} m
            </text>
          </g>
        )}
        {sortedContacts.map((c) => (
          <ContactGlyph
            key={c.id}
            c={c}
            selected={c.id === selected}
            showLabel={
              layers.labels &&
              (c.id === selected ||
                c.requires_human ||
                (crowded ? c.rung >= "R3" : c.rung !== "R0" || !!c.registry_id))
            }
            onSelect={onSelect}
            onHover={(hc) =>
              setHover(hc ? { c: hc, x: mouse.current[0], y: mouse.current[1] } : null)
            }
          />
        ))}
      </svg>
      {hover && (
        <div className="tooltip glass" style={{ left: hover.x, top: hover.y }}>
          <strong className="mono">
            {hover.c.id} · {hover.c.label_text} {pct(hover.c.confidence)}
          </strong>
          <div style={{ margin: "4px 0" }}>
            <RungChip rung={hover.c.rung} name={hover.c.rung_names[hover.c.rung_names.length - 1]} />
          </div>
          <span className="muted">{hover.c.reason}</span>
        </div>
      )}
      {children}
    </div>
  );
}

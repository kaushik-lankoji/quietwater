import { useLayoutEffect, useRef, useState } from "react";
import { pct } from "../format";
import { formatBearing, tierOf, toPolar } from "../radar/geometry";
import type { Contact } from "../types";
import { RiskPill } from "./bits";

const WIDTH = 280;
const GAP = 18;
const EDGE = 16;

export function ContactPopup({
  contact,
  handled,
  watched,
  x,
  y,
  radius,
}: {
  contact: Contact;
  handled?: boolean;
  watched?: boolean;
  x: number;
  y: number;
  radius: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    const h = ref.current?.offsetHeight ?? 240;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const offset = radius + GAP;
    let left = x + offset;
    if (left + WIDTH > vw - EDGE) left = x - offset - WIDTH;
    left = Math.max(EDGE, Math.min(vw - WIDTH - EDGE, left));
    let top = y - h / 2;
    top = Math.max(EDGE, Math.min(vh - h - EDGE, top));
    setPos({ left, top });
  }, [x, y, radius, contact.id]);

  const polar = toPolar(contact.x, contact.y);
  const rungName = contact.rung_names[contact.rung_names.length - 1] ?? "";
  const tier = tierOf(contact.rung, contact.urgency);

  return (
    <div
      ref={ref}
      className="contact-popup"
      role="tooltip"
      style={pos ? { left: pos.left, top: pos.top } : { left: -9999, top: -9999 }}
    >
      <div className="popup-head">
        <span className="popup-title">{contact.label_text}</span>
        <RiskPill tier={tier} handled={handled && tier === "high"} watched={watched} />
      </div>
      <dl className="popup-grid">
        <div>
          <dt>Confidence</dt>
          <dd>{pct(contact.confidence)}</dd>
        </div>
        <div>
          <dt>Distance</dt>
          <dd>{Math.round(polar.distance)} m</dd>
        </div>
        <div>
          <dt>Bearing</dt>
          <dd>{formatBearing(polar.bearing)}</dd>
        </div>
        <div>
          <dt>Speed</dt>
          <dd>{contact.speed_kn} kn</dd>
        </div>
        <div>
          <dt>Heading</dt>
          <dd>{formatBearing(contact.heading)}</dd>
        </div>
        <div>
          <dt>Rung</dt>
          <dd>
            {contact.rung} {rungName}
          </dd>
        </div>
      </dl>
      <p className="popup-reason">{contact.reason}</p>
    </div>
  );
}

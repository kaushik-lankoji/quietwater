import { memo, useEffect, useRef, useState } from "react";
import { RadarEngine } from "../radar/engine";
import type { Contact } from "../types";
import { ContactPopup } from "./ContactPopup";
import { Drone } from "./Drone";

interface Hover {
  id: string;
  x: number;
  y: number;
  radius: number;
}

export const Radar = memo(function Radar({
  contacts,
  run,
  selected,
  handled,
  onSelect,
}: {
  contacts: Contact[];
  handled: ReadonlySet<string>;
  run: number;
  selected: string | null;
  onSelect: (contact: Contact | null) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const engine = useRef<RadarEngine | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const hoverRef = useRef<Hover | null>(null);

  const showHover = (next: Hover | null) => {
    const prev = hoverRef.current;
    if (prev?.id === next?.id && prev?.x === next?.x && prev?.y === next?.y) return;
    hoverRef.current = next;
    setHover(next);
  };

  useEffect(() => {
    const el = canvas.current!;
    const radar = new RadarEngine(el);
    engine.current = radar;
    const fit = () => radar.resize(window.innerWidth, window.innerHeight);
    fit();
    radar.onChange = () => {
      const h = hoverRef.current;
      if (!h) return;
      const echo = radar.echo(h.id);
      if (!echo) {
        radar.hovered = null;
        el.style.cursor = "";
        showHover(null);
        return;
      }
      const pos = radar.position(echo);
      showHover({ id: h.id, x: pos.x, y: pos.y, radius: echo.radius });
    };
    radar.start();
    window.addEventListener("resize", fit);
    return () => {
      window.removeEventListener("resize", fit);
      radar.stop();
      engine.current = null;
    };
  }, []);

  useEffect(() => {
    engine.current?.setContacts(contacts);
  }, [contacts]);

  useEffect(() => {
    if (engine.current) engine.current.handled = handled;
  }, [handled]);

  useEffect(() => {
    engine.current?.reset();
  }, [run]);

  useEffect(() => {
    if (engine.current) engine.current.selected = selected;
  }, [selected]);

  const pick = (e: React.PointerEvent | React.MouseEvent) => {
    const radar = engine.current;
    if (!radar) return null;
    const rect = canvas.current!.getBoundingClientRect();
    return radar.hitTest(e.clientX - rect.left, e.clientY - rect.top);
  };

  const echo = hover ? engine.current?.echo(hover.id) : undefined;
  const live = hover ? contacts.find((c) => c.id === hover.id) ?? echo?.contact : undefined;

  return (
    <div className="radar">
      <canvas
        ref={canvas}
        className="radar-canvas"
        role="img"
        aria-label={`Sonar radar, ${contacts.length} contacts`}
        onPointerMove={(e) => {
          const radar = engine.current;
          if (!radar) return;
          const hit = pick(e);
          radar.hovered = hit?.id ?? null;
          canvas.current!.style.cursor = hit ? "pointer" : "";
          if (!hit) return showHover(null);
          const pos = radar.position(hit);
          showHover({ id: hit.id, x: pos.x, y: pos.y, radius: hit.radius });
        }}
        onPointerLeave={() => {
          if (engine.current) engine.current.hovered = null;
          showHover(null);
        }}
        onClick={(e) => {
          const hit = pick(e);
          onSelect(hit ? contacts.find((c) => c.id === hit.id) ?? hit.contact : null);
        }}
      />
      <Drone />
      {hover && live && <ContactPopup key={hover.id} contact={live} handled={handled.has(live.id)} x={hover.x} y={hover.y} radius={hover.radius} />}
    </div>
  );
});

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { cls } from "../format";
import type { Check, Rung, Urgency } from "../types";
import { Icon } from "./Icon";

export function RungChip({ rung, name, size, solid }: { rung: Rung; name?: string; size?: "lg"; solid?: boolean }) {
  return (
    <span className={cls("rung", rung, size, solid && "solid")}>
      <b>{rung}</b>
      {name}
    </span>
  );
}

export function Rungs({ rungs, names, size, solid }: { rungs: Rung[]; names?: string[]; size?: "lg"; solid?: boolean }) {
  return (
    <span className="rungs">
      {rungs.map((r, i) => (
        <span key={r} className="rungs">
          {i > 0 && <span className="plus">+</span>}
          <RungChip rung={r} name={names?.[i]} size={size} solid={solid} />
        </span>
      ))}
    </span>
  );
}

export function UrgencyTag({ urgency }: { urgency: Urgency }) {
  return (
    <span className={cls("urgency", urgency)}>
      {urgency === "urgent" && <Icon name="alert" size={14} />}
      {urgency}
    </span>
  );
}

export function Checklist({ checks }: { checks: Check[] }) {
  const order = (c: Check) => (c.ruled_out === true ? 0 : c.ruled_out === null ? 1 : 2);
  const sorted = [...checks].sort((a, b) => order(a) - order(b));
  return (
    <div className="checklist" role="list">
      {sorted.map((c) => {
        const state = c.ruled_out === true ? "out" : c.ruled_out === null ? "open" : "flag";
        const word = state === "out" ? "Ruled out" : state === "open" ? "Still open" : "Not ruled out";
        return (
          <div key={c.key} className={cls("check", state)} role="listitem" aria-label={`${c.label}: ${word}. ${c.detail}`}>
            <span className="mark">
              <Icon name={state === "out" ? "check" : state === "open" ? "minus" : "x"} size={14} />
            </span>
            <span className="lbl">{c.label}</span>
            <span className="det" title={c.detail}>
              {c.detail}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function Path({ path }: { path: string[] }) {
  return (
    <span className="path" aria-label={`Path ${path.join(", ")}`}>
      {path.map((p, i) => (
        <span key={`${p}-${i}`}>{p}</span>
      ))}
    </span>
  );
}

export interface Toast {
  id: number;
  text: ReactNode;
  kind?: "error" | "ok";
}

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const push = useCallback((text: ReactNode, kind?: "error" | "ok") => {
    const id = next.current++;
    setToasts((t) => [...t, { id, text, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 6000 : 3500);
  }, []);
  return { toasts, push };
}

export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={cls("toast glass", t.kind)}>
          <Icon name={t.kind === "error" ? "alert" : "check"} size={16} />
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

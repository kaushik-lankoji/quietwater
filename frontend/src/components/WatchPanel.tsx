import { useState } from "react";
import { cls, mmss } from "../format";
import type { HandoffItem } from "../types";
import { Icon } from "./Icon";

/** Contacts the operator chose to keep watching, soonest re-check first. */
export function WatchPanel({ items, active, onOpen }: { items: HandoffItem[]; active: string | null; onOpen: (id: string) => void }) {
  const [open, setOpen] = useState(true);
  const watched = items.filter((i) => i.status === "watching").sort((a, b) => (a.watch_left_s ?? 0) - (b.watch_left_s ?? 0));
  if (watched.length === 0) return null;
  return (
    <section className={cls("watch glass", !open && "collapsed")} aria-label="Watch panel">
      <button type="button" className="watch-head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Icon name="eye" size={18} />
        <span className="watch-title">Watching</span>
        <span className="watch-count">{watched.length}</span>
        <span className="chev">
          <Icon name="chevronDown" size={16} />
        </span>
      </button>
      {open && (
        <ul className="watch-list">
          {watched.map((i) => {
            const d = i.decision;
            return (
              <li key={i.id}>
                <button type="button" className={cls("watch-row", active === i.id && "on")} onClick={() => onOpen(i.id)}>
                  <span className="risk-dot watching" aria-hidden />
                  <span className="watch-main">
                    <span className="watch-id">{d.contact_id}</span>
                    <span className="watch-what">{d.label_text}</span>
                  </span>
                  <span className="watch-time num">{mmss(i.watch_left_s ?? 0)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

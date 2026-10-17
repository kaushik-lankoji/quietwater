import { memo, useMemo, useState } from "react";
import { api } from "../api";
import { cls } from "../format";
import type { Receipt } from "../types";
import { Checklist, Path, Rungs } from "./bits";
import { Icon } from "./Icon";
import { Counterfactuals } from "./Inspector";

type Filter = "all" | "auto" | "human";

const Row = memo(function Row({ r, onSelect }: { r: Receipt; onSelect: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const d = r.decision;
  return (
    <div className={cls("receipt", !r.automated && "human")}>
      <div className="receipt-row">
        <span className="time">{r.clock}</span>
        <button className="cid" onClick={() => onSelect(r.contact_id)} title="Show on map">
          {r.contact_id}
        </button>
        <Rungs rungs={d.rungs} names={d.rung_names} />
        <span className="why" title={d.reason}>
          {d.reason}
        </span>
        <button className="why-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          Why not <Icon name="up" size={13} />
          <Icon name="down" size={13} />
        </button>
      </div>
      {open && (
        <div className="receipt-detail">
          <Counterfactuals d={d} />
          <div className="receipt-meta">
            <Path path={d.path} />
            <span>{r.automated ? "Automated" : "Needs a person"}</span>
            <span>rules v{r.rules_version}</span>
            <span>{d.label_text} · {Math.round(d.confidence * 100)}%</span>
            <span>consequence {d.consequence}</span>
            {d.notice && <span>{d.notice}</span>}
          </div>
          <Checklist checks={d.checks} />
        </div>
      )}
    </div>
  );
});

export function Receipts({
  receipts,
  onSelect,
  collapsed,
  onCollapse,
}: {
  receipts: Receipt[];
  onSelect: (id: string) => void;
  collapsed: boolean;
  onCollapse: (v: boolean) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out: Receipt[] = [];
    for (let i = receipts.length - 1; i >= 0 && out.length < 250; i--) {
      const r = receipts[i];
      if (filter === "auto" && !r.automated) continue;
      if (filter === "human" && r.automated) continue;
      if (q && !r.contact_id.toLowerCase().includes(q) && !r.decision.reason.toLowerCase().includes(q)) continue;
      out.push(r);
    }
    return out;
  }, [receipts, filter, query]);
  const automated = receipts.filter((r) => r.automated).length;

  return (
    <section className="panel receipts" aria-label="Decision receipts">
      <div className="panel-head">
        <button
          className="btn ghost icon-only small"
          aria-label={collapsed ? "Expand receipts" : "Collapse receipts"}
          aria-expanded={!collapsed}
          onClick={() => onCollapse(!collapsed)}
        >
          <span style={{ display: "flex", transform: collapsed ? "rotate(180deg)" : undefined }}>
            <Icon name="chevronDown" />
          </span>
        </button>
        <span className="panel-title">Decision receipts</span>
        <span className="muted" style={{ fontSize: 13 }}>
          {receipts.length} logged · {automated} automated
        </span>
        <span className="spacer" />
        <div className="receipts-tools">
          <div className="segmented" role="group" aria-label="Filter receipts">
            {(
              [
                ["all", "All"],
                ["auto", "Automated"],
                ["human", "Needs you"],
              ] as const
            ).map(([k, label]) => (
              <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>
                {label}
              </button>
            ))}
          </div>
          <input
            className="search"
            placeholder="Contact or word"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search receipts"
          />
          <a className="btn small" href={api.exportUrl("json")} download>
            <Icon name="download" size={15} /> JSON
          </a>
          <a className="btn small" href={api.exportUrl("csv")} download>
            <Icon name="download" size={15} /> CSV
          </a>
        </div>
      </div>
      {!collapsed && (
        <div className="receipt-list">
          {rows.length === 0 ? (
            <div className="empty">No receipts match.</div>
          ) : (
            rows.map((r) => <Row key={r.id + r.seq} r={r} onSelect={onSelect} />)
          )}
        </div>
      )}
    </section>
  );
}

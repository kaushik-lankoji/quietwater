import { memo, useMemo, useState } from "react";
import { api } from "../api";
import { cls, pct } from "../format";
import { tierOf } from "../radar/geometry";
import type { Receipt } from "../types";
import { Checklist, Counterfactuals, Path, RiskDot } from "./bits";
import { Icon } from "./Icon";

type Filter = "all" | "auto" | "human";

const FILTERS: [Filter, string][] = [
  ["all", "All"],
  ["auto", "Automated"],
  ["human", "Needs you"],
];

const Row = memo(function Row({ r, initiallyOpen, onFocus }: { r: Receipt; initiallyOpen: boolean; onFocus: (id: string) => void }) {
  const [open, setOpen] = useState(initiallyOpen);
  const d = r.decision;
  const name = d.rung_names[d.rung_names.length - 1] ?? "";
  return (
    <div className={cls("receipt", open && "open")}>
      <div className="receipt-row">
        <RiskDot tier={tierOf(d.rung, d.urgency)} />
        <div className="receipt-main">
          <div className="receipt-line">
            <button type="button" className="cid link" onClick={() => onFocus(r.contact_id)}>
              {r.contact_id}
            </button>
            <span className="receipt-rung">
              {d.rungs.join(" + ")} {name}
            </span>
            <span className="num muted receipt-time">{r.clock}</span>
          </div>
          <p className="receipt-reason">{d.reason}</p>
          <button type="button" className="why-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            Why not one rung higher or lower?
            <Icon name="chevronDown" size={14} />
          </button>
        </div>
      </div>
      {open && (
        <div className="receipt-detail">
          <Counterfactuals higher={d.why_higher} lower={d.why_lower} />
          <div className="receipt-meta">
            <Path path={d.path} />
            <span>{r.automated ? "Automated" : "Needs a person"}</span>
            <span>rules v{r.rules_version}</span>
            <span>
              {d.label_text} · {pct(d.confidence)}
            </span>
            <span>consequence {d.consequence}</span>
            {d.notice && <span>{d.notice}</span>}
          </div>
          <Checklist checks={d.checks} />
        </div>
      )}
    </div>
  );
});

export function ReceiptsSheetBody({
  receipts,
  focus,
  onFocus,
}: {
  receipts: Receipt[];
  focus: string | null;
  onFocus: (id: string | null) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out: Receipt[] = [];
    for (let i = receipts.length - 1; i >= 0 && out.length < 200; i--) {
      const r = receipts[i];
      if (focus && r.contact_id !== focus) continue;
      if (filter === "auto" && !r.automated) continue;
      if (filter === "human" && r.automated) continue;
      if (q && !r.contact_id.toLowerCase().includes(q) && !r.decision.reason.toLowerCase().includes(q)) continue;
      out.push(r);
    }
    return out;
  }, [receipts, filter, query, focus]);

  return (
    <div className="pane">
      <div className="pane-top receipts-tools">
        <div className="segmented" role="group" aria-label="Filter receipts">
          {FILTERS.map(([k, label]) => (
            <button type="button" key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>
              {label}
            </button>
          ))}
        </div>
        <input className="field-input" placeholder="Search contact or reason" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search receipts" />
        {focus && (
          <button type="button" className="focus-chip" onClick={() => onFocus(null)} aria-label={`Clear contact filter ${focus}`}>
            {focus}
            <Icon name="close" size={14} />
          </button>
        )}
      </div>
      <div className="pane-scroll receipt-list">
        {rows.length === 0 ? (
          <div className="empty">No receipts match.</div>
        ) : (
          rows.map((r, i) => <Row key={`${r.id}-${r.seq}-${focus ?? ""}`} r={r} initiallyOpen={!!focus && i === 0} onFocus={onFocus} />)
        )}
      </div>
      <div className="pane-foot export-bar">
        <span className="muted">Audit log</span>
        <a className="btn small" href={api.exportUrl("json")} download>
          <Icon name="download" size={16} /> JSON
        </a>
        <a className="btn small" href={api.exportUrl("csv")} download>
          <Icon name="download" size={16} /> CSV
        </a>
      </div>
    </div>
  );
}

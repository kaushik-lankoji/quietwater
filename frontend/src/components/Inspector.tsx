import { useState } from "react";
import { pct } from "../format";
import type { Contact, Decision } from "../types";
import { Checklist, Path, Rungs } from "./bits";
import { Icon } from "./Icon";

export function Counterfactuals({ d }: { d: Pick<Decision, "why_higher" | "why_lower"> }) {
  return (
    <>
      <div className="counterfactual">
        <span className="arrow" aria-label="One rung higher">
          <Icon name="up" size={14} />
        </span>
        <span>{d.why_higher}</span>
      </div>
      <div className="counterfactual">
        <span className="arrow" aria-label="One rung lower">
          <Icon name="down" size={14} />
        </span>
        <span>{d.why_lower}</span>
      </div>
    </>
  );
}

export function Inspector({ contact, decision, onClose }: { contact: Contact; decision?: Decision; onClose: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="inspector glass" role="dialog" aria-label={`Contact ${contact.id}`}>
      <div className="inspector-head">
        <strong className="mono">{contact.id}</strong>
        <span>
          {contact.label_text} · {pct(contact.confidence)}
        </span>
        <span className="spacer" />
        <button className="btn ghost icon-only small" onClick={onClose} aria-label="Close inspector">
          <Icon name="close" size={16} />
        </button>
      </div>
      <Rungs rungs={contact.rungs} names={contact.rung_names} />
      <p>{contact.reason}</p>
      <div className="receipt-meta">
        <span>{contact.speed_kn} kn</span>
        <span>hdg {contact.heading}°</span>
        <span>{contact.zone}</span>
        {contact.registry_id && <span>{contact.registry_id}</span>}
      </div>
      {decision && (
        <>
          <Path path={decision.path} />
          <button className="why-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            Why not one rung higher / lower? <Icon name="chevronDown" size={14} />
          </button>
          {open && (
            <>
              <Counterfactuals d={decision} />
              <Checklist checks={decision.checks} />
            </>
          )}
        </>
      )}
    </div>
  );
}

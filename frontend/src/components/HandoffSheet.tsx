import { useState } from "react";
import { cls, latlon, mmss, pct } from "../format";
import type { HandoffItem, RulesData } from "../types";
import { Checklist, Rungs, UrgencyTag } from "./bits";
import { Icon } from "./Icon";

export type Action = "approve" | "reject" | "watch" | "send";

export function needsAttention(i: HandoffItem) {
  return i.status === "pending" || i.status === "watching" || (i.status === "approved" && i.draft_status === "drafted");
}

function Countdown({ item }: { item: HandoffItem }) {
  const total = item.window_s ?? 1;
  const left = item.remaining_s;
  const over = left < 0;
  const frac = over ? 1 : Math.max(0, Math.min(1, left / total));
  const r = 16;
  const c = 2 * Math.PI * r;
  return (
    <div className={cls("countdown", over && "overdue", !over && frac < 0.25 && "low")} aria-label={over ? `Overdue by ${mmss(left)}` : `${mmss(left)} left`}>
      <svg width={38} height={38} viewBox="0 0 38 38" aria-hidden>
        <circle cx={19} cy={19} r={r} className="countdown-track" />
        <circle cx={19} cy={19} r={r} className="countdown-fill" strokeDasharray={c} strokeDashoffset={c * (1 - frac)} transform="rotate(-90 19 19)" />
      </svg>
      <div>
        <div className="countdown-time">
          {over ? "+" : ""}
          {mmss(left)}
        </div>
        <div className="countdown-label">{over ? "overdue" : "to respond"}</div>
      </div>
    </div>
  );
}

function Decide({ item, rules, onAct, busy }: { item: HandoffItem; rules: RulesData; onAct: (item: HandoffItem, a: Action) => void; busy: boolean }) {
  const d = item.decision;
  const open = item.status === "pending" || item.status === "watching";
  const awaitingSend = item.status === "approved" && item.draft_status === "drafted";
  const target = rules.modes[d.track].handoff_target;
  return (
    <section className="decide" aria-label="What to approve">
      <div className="decide-head">
        <span className="eyebrow">We recommend</span>
        <Rungs rungs={d.rungs} names={d.rung_names} />
      </div>
      <p className="ask-rec">{d.recommendation}</p>
      {d.drift && (
        <p className="drift">
          Drift {d.drift.speed_kn} kn toward {d.drift.heading}°
          {d.drift.eta_critical && ` · reaches ${d.drift.eta_critical.zone} in ~${Math.round(d.drift.eta_critical.seconds / 60)} min`}
        </p>
      )}
      {open && (
        <div className="handoff-actions">
          <button type="button" className="btn primary large" disabled={busy} onClick={() => onAct(item, "approve")}>
            <Icon name="check" size={20} /> Approve
            <kbd>A</kbd>
          </button>
          <div className="handoff-secondary">
            <button type="button" className="btn large" disabled={busy} onClick={() => onAct(item, "reject")}>
              Reject
            </button>
            <button type="button" className="btn large" disabled={busy} onClick={() => onAct(item, "watch")}>
              Keep watching
            </button>
          </div>
        </div>
      )}
      {!open && (
        <div className="resolved">
          <Icon name="check" size={18} />
          <span>
            {item.status === "approved" ? "Approved" : item.status === "rejected" ? "Rejected" : "Stood down"} by {item.actor} at {item.resolved_clock}
          </span>
        </div>
      )}
      {awaitingSend && (
        <button type="button" className="btn primary large" disabled={busy} onClick={() => onAct(item, "send")}>
          <Icon name="send" size={18} /> Send drafted alert to {target}
        </button>
      )}
    </section>
  );
}

function Card({ item, rules, onAct, busy }: { item: HandoffItem; rules: RulesData; onAct: (item: HandoffItem, a: Action) => void; busy: boolean }) {
  const d = item.decision;
  const [copied, setCopied] = useState(false);
  const open = item.status === "pending" || item.status === "watching";
  const awaitingSend = item.status === "approved" && item.draft_status === "drafted";
  const target = rules.modes[d.track].handoff_target;
  const asset = d.focus_asset;

  return (
    <article className={cls("handoff", d.urgency)} aria-label={`Hand-off ${item.id} for ${d.contact_id}`}>
      <div className="handoff-top">
        <div className="handoff-tags">
          <UrgencyTag urgency={d.urgency} />
          <span className="cid">{d.contact_id}</span>
          {item.status === "watching" && <span className="status-pill">watching</span>}
          {item.contact_lost && <span className="status-pill">lost on sonar</span>}
        </div>
        {open && <Countdown item={item} />}
      </div>
      <p className="handoff-reason">{d.reason}</p>

      <section className="handoff-section" aria-label="What is it">
        <span className="eyebrow">What it is</span>
        <div className="what">
          <h3>{d.track === "recovery" ? rules.recovery.lost_vehicle_id : d.label_text}</h3>
          <span className="conf" aria-label={`Confidence ${pct(d.confidence)}`}>
            <span className="conf-bar">
              <span style={{ width: pct(d.confidence) }} />
            </span>
            {pct(d.confidence)}
          </span>
        </div>
        <dl className="facts">
          <div>
            <dt>Size</dt>
            <dd>{d.size_m.toFixed(1)} m</dd>
          </div>
          <div>
            <dt>Speed</dt>
            <dd>
              {d.speed_kn} kn · {d.heading}°
            </dd>
          </div>
          {asset && (
            <div>
              <dt>Nearest</dt>
              <dd>
                {asset.distance_m} m · {asset.name}
              </dd>
            </div>
          )}
          <div>
            <dt>Position</dt>
            <dd>{latlon(d.position, rules.harbor.origin)}</dd>
          </div>
        </dl>
      </section>

      <section className="handoff-section" aria-label="What has been ruled out">
        <span className="eyebrow">What&rsquo;s ruled out</span>
        <Checklist checks={d.checks} />
      </section>

      {item.draft && (
        <details className="draft" open={awaitingSend}>
          <summary>
            <Icon name="file" size={18} />
            <span>Handoff package · {target}</span>
            <span className="status-pill">{item.draft_status === "sent" ? "sent" : "drafted"}</span>
            <span className="chev">
              <Icon name="chevronDown" size={16} />
            </span>
          </summary>
          {item.steps.length > 0 && (
            <div className="steps">
              {item.steps.map((s, i) => (
                <div key={i}>
                  <span className="num">{s.clock}</span>
                  <span>
                    {s.rungs} <span className="muted">· {s.automated ? "automated" : "needs you"}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
          <pre>{item.draft.body}</pre>
          <div className="draft-actions">
            <button
              type="button"
              className="btn small"
              onClick={() => {
                navigator.clipboard?.writeText(item.draft!.body);
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1500);
              }}
            >
              <Icon name="copy" size={16} /> {copied ? "Copied" : "Copy"}
            </button>
            <span className="muted">{item.draft_status === "sent" ? "Sent by you. Logged in the audit." : "Quietwater never sends this itself."}</span>
            {item.draft_status !== "sent" && (
              <button
                type="button"
                className="btn small"
                disabled={busy || item.status !== "approved"}
                title={item.status !== "approved" ? "Approve first" : undefined}
                onClick={() => onAct(item, "send")}
              >
                <Icon name="send" size={16} /> Send
              </button>
            )}
          </div>
        </details>
      )}
    </article>
  );
}

export function HandoffSheetBody({
  items,
  rules,
  activeId,
  onActive,
  onAct,
  busy,
  quiet,
}: {
  items: HandoffItem[];
  rules: RulesData;
  activeId: string | null;
  onActive: (id: string) => void;
  onAct: (item: HandoffItem, a: Action) => void;
  busy: boolean;
  quiet: number;
}) {
  const queue = items.filter(needsAttention);
  const selected = items.find((i) => i.id === activeId);
  const active = selected ?? queue[0];
  const recent = items.filter((i) => !needsAttention(i) && i !== active).slice(0, 4);
  const idx = active ? queue.indexOf(active) : -1;

  return (
    <div className="pane">
      {queue.length > 1 && (
        <div className="pane-top queue-nav">
          <button
            type="button"
            className="icon-button small"
            aria-label="Previous in queue"
            onClick={() => onActive(queue[(Math.max(idx, 0) - 1 + queue.length) % queue.length].id)}
          >
            <Icon name="chevronLeft" size={18} />
          </button>
          <span className="num">
            {idx >= 0 ? idx + 1 : "–"} of {queue.length}
          </span>
          <button type="button" className="icon-button small" aria-label="Next in queue" onClick={() => onActive(queue[(idx + 1) % queue.length].id)}>
            <Icon name="chevronRight" size={18} />
          </button>
        </div>
      )}
      <div className="pane-scroll handoff-body">
        {active ? (
          <Card key={active.id} item={active} rules={rules} onAct={onAct} busy={busy} />
        ) : (
          <div className="empty">
            <Icon name="wave" size={32} />
            <span className="empty-title">All quiet</span>
            <span>
              {quiet} contact{quiet === 1 ? "" : "s"} handled without you. A card appears here when something needs a person.
            </span>
          </div>
        )}
        {(queue.length > 1 || recent.length > 0) && (
          <div className="queue-list">
            <span className="eyebrow">Queue</span>
            {queue
              .filter((i) => i !== active)
              .map((i) => (
                <button type="button" key={i.id} className="queue-row" onClick={() => onActive(i.id)}>
                  <UrgencyTag urgency={i.decision.urgency} />
                  <span className="cid">{i.contact_id}</span>
                  <span className="queue-what">{i.decision.recommendation}</span>
                  <span className="num muted">{i.remaining_s < 0 ? "overdue" : mmss(i.remaining_s)}</span>
                </button>
              ))}
            {recent.map((i) => (
              <button type="button" key={i.id} className="queue-row done" onClick={() => onActive(i.id)}>
                <span className="status-pill">{i.status.replace("_", " ")}</span>
                <span className="cid">{i.contact_id}</span>
                <span className="queue-what">{i.note ?? i.decision.recommendation}</span>
                <span className="num muted">{i.resolved_clock?.slice(0, 5)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {active && (
        <div className="pane-foot">
          <Decide item={active} rules={rules} onAct={onAct} busy={busy} />
        </div>
      )}
    </div>
  );
}

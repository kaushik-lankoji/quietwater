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
  const r = 19;
  const c = 2 * Math.PI * r;
  const color = over ? "var(--danger)" : frac < 0.25 ? "var(--r4)" : "var(--accent)";
  return (
    <div className={cls("countdown", over && "overdue")} aria-label={over ? `Overdue by ${mmss(left)}` : `${mmss(left)} left`}>
      <svg className="ring-svg" width={46} height={46} viewBox="0 0 46 46" aria-hidden>
        <circle cx={23} cy={23} r={r} stroke="var(--surface-3)" />
        <circle
          cx={23}
          cy={23}
          r={r}
          stroke={color}
          strokeDasharray={c}
          strokeDashoffset={c * (1 - frac)}
          strokeLinecap="round"
          transform="rotate(-90 23 23)"
          style={{ transition: "stroke-dashoffset 0.5s linear" }}
        />
      </svg>
      <div>
        <div className="time">
          {over ? "+" : ""}
          {mmss(left)}
        </div>
        <div className="label">{over ? "overdue" : "to respond"}</div>
      </div>
    </div>
  );
}

function Card({
  item,
  rules,
  onAct,
  busy,
}: {
  item: HandoffItem;
  rules: RulesData;
  onAct: (item: HandoffItem, a: Action) => void;
  busy: boolean;
}) {
  const d = item.decision;
  const [copied, setCopied] = useState(false);
  const open = item.status === "pending" || item.status === "watching";
  const awaitingSend = item.status === "approved" && item.draft_status === "drafted";
  const target = rules.modes[d.track].handoff_target;
  const asset = d.focus_asset;

  return (
    <article className={cls("handoff-card", d.urgency)} aria-label={`Hand-off ${item.id} for ${d.contact_id}`}>
      <div className="hc-top">
        <UrgencyTag urgency={d.urgency} />
        <span className="cid">{d.contact_id}</span>
        {item.status === "watching" && <span className="status-pill watching">watching</span>}
        {item.contact_lost && <span className="status-pill">lost on sonar</span>}
        <span className="spacer" />
        {open && <Countdown item={item} />}
      </div>

      <section className="what" aria-label="What is it">
        <span className="eyebrow">What is it</span>
        <div className="what-label">
          <h2>{d.track === "recovery" ? rules.recovery.lost_vehicle_id : d.label_text}</h2>
          <span className="conf" aria-label={`Confidence ${pct(d.confidence)}`}>
            <span className="conf-bar">
              <span style={{ width: pct(d.confidence) }} />
            </span>
            {pct(d.confidence)}
          </span>
        </div>
        <div className="facts-line">
          <span>
            <b>{d.size_m.toFixed(1)} m</b>
          </span>
          <span>
            <b>{d.speed_kn} kn</b> hdg <b>{d.heading}°</b>
          </span>
          <span className="mono">{latlon(d.position, rules.harbor.origin)}</span>
          {asset && (
            <span>
              <b>{asset.distance_m} m</b> from {asset.name}
            </span>
          )}
        </div>
      </section>

      <p className="reason">{d.reason}</p>

      <section aria-label="What has been ruled out">
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          What&rsquo;s been ruled out
        </div>
        <Checklist checks={d.checks} />
      </section>

      <section className="ask" aria-label="What am I asked to do">
        <span className="eyebrow">We recommend</span>
        <Rungs rungs={d.rungs} names={d.rung_names} size="lg" solid />
        <p className="ask-rec">{d.recommendation}</p>
        {d.drift && (
          <div className="facts-line">
            <span>
              Drift <b>{d.drift.speed_kn} kn</b> toward <b>{d.drift.heading}°</b>
            </span>
            {d.drift.eta_critical && (
              <span>
                reaches <b>{d.drift.eta_critical.zone}</b> in ~{Math.round(d.drift.eta_critical.seconds / 60)} min
              </span>
            )}
          </div>
        )}
        {open && (
          <div className="actions">
            <button className="btn approve" disabled={busy} onClick={() => onAct(item, "approve")}>
              <span className="btn-label">
                <Icon name="check" size={20} /> Approve
              </span>
              <kbd>A</kbd>
            </button>
            <button className="btn danger-outline" disabled={busy} onClick={() => onAct(item, "reject")}>
              Reject <kbd>R</kbd>
            </button>
            <button className="btn" disabled={busy} onClick={() => onAct(item, "watch")}>
              Keep watching <kbd>W</kbd>
            </button>
          </div>
        )}
        {!open && (
          <div className="resolved-banner">
            <Icon name="check" />
            <span>
              {item.status === "approved" ? "Approved" : item.status === "rejected" ? "Rejected" : "Stood down"} by{" "}
              {item.actor} at {item.resolved_clock}
            </span>
          </div>
        )}
        {awaitingSend && (
          <button className="btn primary send-now" disabled={busy} onClick={() => onAct(item, "send")}>
            <Icon name="send" size={18} /> Send drafted alert to {target}
          </button>
        )}
      </section>

      {item.draft && (
        <details className="draft" open={awaitingSend}>
          <summary>
            <Icon name="file" size={16} />
            Handoff package · alert to {target}
            <span style={{ flex: 1 }} />
            {item.draft_status === "sent" ? (
              <span className="status-pill approved">sent</span>
            ) : (
              <span className="status-pill">drafted</span>
            )}
            <span className="chev">
              <Icon name="chevronDown" size={16} />
            </span>
          </summary>
          {item.steps.length > 0 && (
            <div className="steps">
              {item.steps.map((s, i) => (
                <div key={i}>
                  <span className="mono muted">{s.clock}</span>
                  <span>
                    {s.rungs} {s.automated ? <span className="muted">· automated</span> : <span className="muted">· needs you</span>}
                  </span>
                </div>
              ))}
            </div>
          )}
          <pre>{item.draft.body}</pre>
          <div className="draft-actions">
            <button
              className="btn small"
              onClick={() => {
                navigator.clipboard?.writeText(item.draft!.body);
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1500);
              }}
            >
              <Icon name="copy" size={15} /> {copied ? "Copied" : "Copy"}
            </button>
            <span style={{ flex: 1 }} className="muted">
              {item.draft_status === "sent" ? "Sent by you. Logged in the audit." : "Quietwater never sends this itself."}
            </span>
            {item.draft_status !== "sent" && (
              <button
                className={cls("btn", awaitingSend && "primary")}
                disabled={busy || item.status !== "approved"}
                title={item.status !== "approved" ? "Approve first" : undefined}
                onClick={() => onAct(item, "send")}
              >
                <Icon name="send" size={15} /> Send to {target.split(" ")[0]}
              </button>
            )}
          </div>
        </details>
      )}
    </article>
  );
}

export function HandoffPanel({
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
  const pending = queue.filter((i) => i.status === "pending").length;
  const active = queue.find((i) => i.id === activeId) ?? queue[0];
  const recent = items.filter((i) => !needsAttention(i)).slice(0, 4);
  const idx = active ? queue.indexOf(active) : -1;

  return (
    <section className="panel handoff" aria-label="Hand-off">
      <div className="panel-head">
        <span className="panel-title">Needs you</span>
        <span className={cls("queue-count", pending === 0 && "zero")}>{pending}</span>
        <span className="spacer" />
        {queue.length > 1 && (
          <>
            <button
              className="btn ghost icon-only small"
              aria-label="Previous in queue"
              onClick={() => onActive(queue[(idx - 1 + queue.length) % queue.length].id)}
            >
              <Icon name="chevronLeft" />
            </button>
            <span className="mono muted" style={{ fontSize: 13 }}>
              {idx + 1} / {queue.length}
            </span>
            <button
              className="btn ghost icon-only small"
              aria-label="Next in queue"
              onClick={() => onActive(queue[(idx + 1) % queue.length].id)}
            >
              <Icon name="chevronRight" />
            </button>
          </>
        )}
      </div>
      <div className="handoff-scroll">
      {active ? (
        <Card key={active.id} item={active} rules={rules} onAct={onAct} busy={busy} />
      ) : (
        <div className="empty">
          <span className="wave">
            <Icon name="wave" size={40} />
          </span>
          <span className="big">All quiet</span>
          <span>
            {quiet} contact{quiet === 1 ? "" : "s"} handled without you. You&rsquo;ll see a card here when something
            needs a person.
          </span>
        </div>
      )}
      {(queue.length > 1 || recent.length > 0) && (
        <div className="queue-list">
          {queue
            .filter((i) => i !== active)
            .map((i) => (
              <button key={i.id} className="queue-row" onClick={() => onActive(i.id)}>
                <UrgencyTag urgency={i.decision.urgency} />
                <span className="cid">{i.contact_id}</span>
                <span className="what">{i.decision.recommendation}</span>
                <span className="mono muted">{i.remaining_s < 0 ? "overdue" : mmss(i.remaining_s)}</span>
              </button>
            ))}
          {recent.map((i) => (
            <div key={i.id} className="queue-row" aria-current={false}>
              <span className={cls("status-pill", i.status)}>{i.status.replace("_", " ")}</span>
              <span className="cid">{i.contact_id}</span>
              <span className="what">{i.note ?? i.decision.recommendation}</span>
              <span className="mono muted">{i.resolved_clock?.slice(0, 5)}</span>
            </div>
          ))}
        </div>
      )}
      </div>
    </section>
  );
}

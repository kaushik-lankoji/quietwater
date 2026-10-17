import { useState, type ReactNode } from "react";
import { cls, latlon, mmss, pct } from "../format";
import type { HandoffAction, HandoffItem, ItemStatus, RulesData } from "../types";
import { Checklist, UrgencyTag } from "./bits";
import { Icon, type IconName } from "./Icon";

export type ActExtra = { body?: string; confirm?: boolean };
export type OnAct = (item: HandoffItem, action: HandoffAction, extra?: ActExtra) => void;

const ACTIVE: ItemStatus[] = ["pending", "expired", "watching", "hold_requesting", "hold_active", "hold_failed", "notice_review", "notice_sent"];
const WAITING: ItemStatus[] = ["pending", "expired"];

/** Items that belong in the operator's queue: still open, in progress, or dismissed with Undo still live. */
export function needsAttention(i: HandoffItem) {
  return ACTIVE.includes(i.status) || (i.status === "dismissed" && (i.undo_left_s ?? 0) > 0);
}

export const isWaiting = (i: HandoffItem) => WAITING.includes(i.status);
export const holdStep = (i: HandoffItem) => i.plan.find((p) => p.kind === "hold");

function agency(item: HandoffItem, rules: RulesData) {
  return item.draft?.to ?? rules.modes[item.decision.track].handoff_target;
}

/** "USCG Sector Los Angeles-Long Beach" -> "USCG", "USC Wrigley Marine Lab ops desk" -> "USC Wrigley Marine Lab". */
function shortAgency(name: string) {
  return name.split(/\s+(?:Sector|ops desk|operations)\b/)[0].trim() || name;
}

function entered(item: HandoffItem) {
  return item.history[item.history.length - 1]?.clock ?? item.created_clock;
}

function summary(reason: string) {
  const first = reason.split(/(?<=\.)\s/)[0];
  return first.length > 8 ? first : reason;
}

function Banner({ icon, tone, title, sub, children }: { icon: IconName; tone: "ok" | "warn" | "bad" | "info" | "busy"; title: string; sub: ReactNode; children?: ReactNode }) {
  return (
    <div className={cls("state-banner", tone)} role="status">
      <span className="state-icon">
        <Icon name={icon} size={18} />
      </span>
      <div className="state-text">
        <span className="state-title">{title}</span>
        <span className="state-sub">{sub}</span>
      </div>
      {children}
    </div>
  );
}

function HoldTimer({ item }: { item: HandoffItem }) {
  const left = item.hold_left_s ?? 0;
  const up = left <= 0;
  return (
    <div className={cls("hold-timer", up && "up")}>
      <span className="hold-time num">{up ? "00:00" : mmss(left)}</span>
      <span className="hold-label">{up ? "Hold time is up. It stays in place until you lift it." : "hold time left"}</span>
    </div>
  );
}

function StateBanner({ item, rules }: { item: HandoffItem; rules: RulesData }) {
  const at = entered(item);
  const to = agency(item, rules);
  const hold = item.hold;
  switch (item.status) {
    case "expired":
      return <Banner icon="bell" tone="bad" title="No response in time · backup officer paged" sub={`On screen only. Nothing was sent. ${at}`} />;
    case "watching":
      return <Banner icon="eye" tone="info" title={`Keep watching · re-checks in ${mmss(item.watch_left_s ?? 0)}`} sub={`Since ${at}. Nothing is sent.`} />;
    case "hold_requesting":
      return <Banner icon="sync" tone="busy" title="Sending hold request" sub={`To ${hold?.asset} operations · ${at}`} />;
    case "hold_failed":
      return <Banner icon="alert" tone="bad" title="Hold request failed" sub={`${hold?.asset} operations didn't confirm. Nothing is paused. ${at}`} />;
    case "hold_active":
      return (
        <Banner icon="hold" tone="ok" title="Hold active" sub={`${capital(hold?.operation)} paused at ${hold?.asset} · since ${hold?.confirmed_clock ?? at}`}>
          <HoldTimer item={item} />
        </Banner>
      );
    case "notice_review":
      return <Banner icon="file" tone="info" title={`Reviewing notice to ${shortAgency(to)}`} sub={`Not sent. Opened ${at}${item.draft_edited ? " · edited" : ""}`} />;
    case "notice_sent":
      return (
        <Banner icon="send" tone="ok" title={`Notice sent to ${shortAgency(to)}`} sub={`${at} by ${item.actor} · logged in the audit`}>
          {hold?.status === "active" && <HoldTimer item={item} />}
        </Banner>
      );
    case "dismissed":
      return <Banner icon="x" tone="info" title="Dismissed" sub={`Still tracked. Re-alerts if it gets worse. ${at}`} />;
    case "resolved":
      return <Banner icon="check" tone="ok" title="Resolved" sub={`${at} by ${item.actor}`} />;
    case "lifted":
      return <Banner icon="check" tone="ok" title="Hold lifted" sub={`${capital(hold?.operation)} can resume at ${hold?.asset} · ${at} by ${item.actor}`} />;
    case "stood_down":
      return <Banner icon="check" tone="ok" title="Stood down" sub={`No longer needs a person. ${at}`} />;
    default:
      return null;
  }
}

function capital(s?: string) {
  return s ? s[0].toUpperCase() + s.slice(1) : "";
}

function Plan({ item }: { item: HandoffItem }) {
  const hasHold = Boolean(holdStep(item));
  if (item.plan.length === 0) return null;
  return (
    <section className="plan" aria-label={hasHold ? "If you approve" : "Next step"}>
      <span className="eyebrow">{hasHold ? "If you approve" : "Next step"}</span>
      <ol>
        {item.plan.map((p, i) => (
          <li key={p.kind}>
            <span className="plan-n">{i + 1}</span>
            <div className="plan-text">
              <span className="plan-title">{p.kind === "notice" && item.draft ? `Notice to ${shortAgency(item.draft.to)}` : p.title}</span>
              <span className="plan-detail">{p.detail}</span>
            </div>
            <span className="rung-tag">{p.rung}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function NoticeDraft({ item, editing, text, onText }: { item: HandoffItem; editing: boolean; text: string; onText: (t: string) => void }) {
  const draft = item.draft!;
  return (
    <section className="notice" aria-label="Notice draft">
      <dl className="notice-head">
        <div>
          <dt>To</dt>
          <dd>{draft.to}</dd>
        </div>
        <div>
          <dt>Subject</dt>
          <dd>{draft.subject}</dd>
        </div>
      </dl>
      {editing ? (
        <textarea className="notice-edit" value={text} onChange={(e) => onText(e.target.value)} aria-label="Notice text" spellCheck />
      ) : (
        <pre className="notice-body">{draft.body}</pre>
      )}
    </section>
  );
}

function Evidence({ item, rules }: { item: HandoffItem; rules: RulesData }) {
  const d = item.decision;
  const asset = d.focus_asset;
  return (
    <details className="evidence">
      <summary>
        <span>What it is · what&rsquo;s ruled out</span>
        <span className="chev">
          <Icon name="chevronDown" size={16} />
        </span>
      </summary>
      <div className="evidence-body">
        <div className="what">
          <h4>{d.track === "recovery" ? rules.recovery.lost_vehicle_id : d.label_text}</h4>
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
        <Checklist checks={d.checks} />
        {item.history.length > 1 && (
          <div className="timeline">
            <span className="eyebrow">Timeline</span>
            {item.history.map((h, i) => (
              <div key={i}>
                <span className="num">{h.clock}</span>
                <span>
                  {h.to.replace("_", " ")} <span className="muted">· {h.actor}</span>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

function Choice({ label, help, onClick, disabled }: { label: string; help: string; onClick: () => void; disabled: boolean }) {
  return (
    <div className="choice">
      <button type="button" className="btn" disabled={disabled} onClick={onClick}>
        {label}
      </button>
      <span className="choice-help">{help}</span>
    </div>
  );
}

function Actions({
  item,
  rules,
  onAct,
  busy,
  editing,
  setEditing,
  text,
  setText,
}: {
  item: HandoffItem;
  rules: RulesData;
  onAct: OnAct;
  busy: boolean;
  editing: boolean;
  setEditing: (e: boolean) => void;
  text: string;
  setText: (t: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const to = agency(item, rules);
  const short = shortAgency(to);
  const hold = holdStep(item);
  const canReview = Boolean(item.draft) && item.draft_status !== "sent";
  const snooze = mmss(rules.alert_budget.keep_watching_snooze_s);
  const holdMins = mmss(rules.handoff?.hold_s ?? 1800);
  const go = (a: HandoffAction, extra?: ActExtra) => onAct(item, a, extra);
  const review = (primary: boolean) =>
    canReview && (
      <button type="button" className={cls("btn wrap", primary && "primary large")} disabled={busy} onClick={() => go("review")}>
        <Icon name="file" size={18} /> Review {short} notice
      </button>
    );
  const holdControls = (primary: boolean) =>
    item.hold?.status === "active" && (
      <div className={cls(item.hold.time_up && "pair")}>
        <button type="button" className={cls("btn", primary && "primary large")} disabled={busy} onClick={() => go("lift")}>
          <Icon name="play" size={16} /> Lift hold
        </button>
        {item.hold.time_up && (
          <button type="button" className="btn" disabled={busy} onClick={() => go("extend")}>
            Extend {holdMins}
          </button>
        )}
      </div>
    );

  switch (item.status) {
    case "pending":
    case "expired":
      return (
        <div className="actions">
          {hold ? (
            <button type="button" className="btn primary large wrap" disabled={busy} onClick={() => go("approve")}>
              <Icon name="check" size={20} /> Approve: {hold.title}
              <kbd>A</kbd>
            </button>
          ) : null}
          {review(!hold)}
          <div className="pair">
            <Choice label="Dismiss" help="Still tracked; re-alerts if worse" disabled={busy} onClick={() => go("dismiss")} />
            <Choice label="Keep watching" help={`Re-checks in ${snooze}; sends nothing`} disabled={busy} onClick={() => go("watch")} />
          </div>
        </div>
      );
    case "watching":
      return (
        <div className="actions">
          <button type="button" className="btn primary large" disabled={busy} onClick={() => go("escalate")}>
            <Icon name="up" size={18} /> Escalate now
          </button>
          <Choice label="Dismiss" help="Still tracked; re-alerts if worse" disabled={busy} onClick={() => go("dismiss")} />
        </div>
      );
    case "hold_requesting":
      return (
        <div className="actions">
          <button type="button" className="btn primary large" disabled>
            <span className="spinner small" /> Waiting for {item.hold?.asset}
          </button>
        </div>
      );
    case "hold_failed":
      return (
        <div className="actions">
          <button type="button" className="btn primary large" disabled={busy} onClick={() => go("retry")}>
            <Icon name="replay" size={18} /> Retry hold request
          </button>
          <div className="pair">
            {review(false)}
            <button type="button" className="btn" disabled={busy} onClick={() => go("resolve")}>
              Close as resolved
            </button>
          </div>
        </div>
      );
    case "hold_active":
      return (
        <div className="actions">
          {review(true)}
          {holdControls(!canReview)}
        </div>
      );
    case "notice_review":
      if (editing)
        return (
          <div className="actions">
            <button
              type="button"
              className="btn primary large"
              disabled={busy || !text.trim()}
              onClick={() => {
                go("edit", { body: text });
                setEditing(false);
              }}
            >
              <Icon name="check" size={18} /> Save changes
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => setEditing(false)}>
              Discard changes
            </button>
          </div>
        );
      if (confirming)
        return (
          <div className="actions confirm" role="alertdialog" aria-label={`Send to ${to}?`}>
            <div className="confirm-text">
              <span className="confirm-title">Send to {short}?</span>
              <span className="choice-help">{to}</span>
              <span className="choice-help">This goes out now. There is no Undo.</span>
            </div>
            <button
              type="button"
              className="btn primary large danger"
              disabled={busy}
              onClick={() => {
                go("send", { confirm: true });
                setConfirming(false);
              }}
            >
              <Icon name="send" size={18} /> Send now
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => setConfirming(false)}>
              Back
            </button>
          </div>
        );
      return (
        <div className="actions">
          <button type="button" className="btn primary large wrap" disabled={busy} onClick={() => setConfirming(true)}>
            <Icon name="send" size={18} /> Send to {short}
          </button>
          <div className="pair">
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                setText(item.draft?.body ?? "");
                setEditing(true);
              }}
            >
              <Icon name="edit" size={16} /> Edit
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => go("cancel")}>
              Cancel
            </button>
          </div>
        </div>
      );
    case "notice_sent":
      return (
        <div className="actions">
          {holdControls(true) || (
            <button type="button" className="btn primary large" disabled={busy} onClick={() => go("resolve")}>
              <Icon name="check" size={18} /> Mark resolved
            </button>
          )}
        </div>
      );
    case "dismissed":
      return (item.undo_left_s ?? 0) > 0 ? (
        <div className="actions">
          <button type="button" className="btn primary large" disabled={busy} onClick={() => go("undo")}>
            <Icon name="undo" size={18} /> Undo · {Math.ceil(item.undo_left_s ?? 0)}s
          </button>
        </div>
      ) : null;
    default:
      return null;
  }
}

function Card({ item, rules, onAct, busy }: { item: HandoffItem; rules: RulesData; onAct: OnAct; busy: boolean }) {
  const d = item.decision;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const review = item.status === "notice_review" && item.draft;
  const showPlan = isWaiting(item);

  return (
    <>
      <div className="pane-scroll handoff-body">
        <article className={cls("handoff", d.urgency)} aria-label={`Contact ${d.contact_id}`}>
          {(d.urgency === "urgent" || item.contact_lost) && (
            <div className="handoff-top">
              <div className="handoff-tags">
                {d.urgency === "urgent" && <UrgencyTag urgency={d.urgency} />}
                {item.contact_lost && <span className="status-pill">lost on sonar</span>}
              </div>
            </div>
          )}
          <p className="handoff-summary">{summary(d.reason)}</p>
          <StateBanner item={item} rules={rules} />
          {showPlan && <Plan item={item} />}
          {review && <NoticeDraft item={item} editing={editing} text={text} onText={setText} />}
          <Evidence item={item} rules={rules} />
        </article>
      </div>
      <div className="pane-foot">
        <Actions item={item} rules={rules} onAct={onAct} busy={busy} editing={editing} setEditing={setEditing} text={text} setText={setText} />
        <p className="handoff-footnote">If no one responds, the backup officer is paged. Nothing goes out automatically.</p>
      </div>
    </>
  );
}

export function QueueNav({ queue, active, onActive }: { queue: HandoffItem[]; active?: HandoffItem; onActive: (id: string) => void }) {
  if (queue.length < 2) return null;
  const idx = active ? queue.indexOf(active) : -1;
  const step = (n: number) => onActive(queue[(Math.max(idx, 0) + n + queue.length) % queue.length].id);
  return (
    <div className="queue-nav">
      <button type="button" className="icon-button small" aria-label="Previous in queue" onClick={() => step(-1)}>
        <Icon name="chevronLeft" size={18} />
      </button>
      <span className="num">
        {idx >= 0 ? idx + 1 : "–"} of {queue.length}
      </span>
      <button type="button" className="icon-button small" aria-label="Next in queue" onClick={() => step(1)}>
        <Icon name="chevronRight" size={18} />
      </button>
    </div>
  );
}

export function HandoffSheetBody({
  active,
  rules,
  onAct,
  busy,
  quiet,
}: {
  active?: HandoffItem;
  rules: RulesData;
  onAct: OnAct;
  busy: boolean;
  quiet: number;
}) {
  return (
    <div className="pane">
      {active ? (
        <Card key={active.id} item={active} rules={rules} onAct={onAct} busy={busy} />
      ) : (
        <div className="pane-scroll handoff-body">
          <div className="empty">
            <span className="all-clear">
              <Icon name="check" size={28} />
            </span>
            <span className="empty-title">All clear</span>
            <span>
              {quiet} handled quietly. A card appears here when something needs a person.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

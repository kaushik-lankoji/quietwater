import { cls, rungVar } from "../format";
import { RUNGS, type Budget, type ModeText } from "../types";

function Spark({ trace, capacity }: { trace: number[]; capacity: number }) {
  const w = 300;
  const h = 26;
  const max = Math.max(capacity, ...trace, 1);
  const pts = trace.length > 1 ? trace : [0, 0];
  const step = w / (pts.length - 1);
  const y = (v: number) => h - 2 - (v / max) * (h - 4);
  const line = pts.map((v, i) => `${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden style={{ height: h }}>
      <line x1={0} x2={w} y1={y(capacity)} y2={y(capacity)} stroke="var(--r5)" strokeDasharray="4 4" strokeOpacity={0.6} vectorEffect="non-scaling-stroke" />
      <polyline points={`0,${h} ${line} ${w},${h}`} fill="var(--accent-soft)" stroke="none" />
      <polyline points={line} fill="none" stroke="var(--accent)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function AlertBudget({ budget, texts }: { budget: Budget; texts: ModeText }) {
  const cap = Math.max(1, Math.round(budget.capacity));
  const ratio = budget.load / budget.capacity;
  const total = RUNGS.reduce((n, r) => n + budget.rung_counts[r], 0) || 1;
  const asks = budget.seen - budget.quiet;
  return (
    <section className="panel budget" aria-label="Alert budget">
      <div className="budget-strip">
        <div className="stat quiet" title="Contacts that never needed a person">
          <div className="n">{budget.quiet}</div>
          <div className="l">handled quietly</div>
        </div>
        <div className={cls("stat need", budget.need_you > 0 && "hot")} title="Hand-offs waiting on you now">
          <div className="n">{budget.need_you}</div>
          <div className="l">need you{budget.watching > 0 ? ` · ${budget.watching} watching` : ""}</div>
        </div>
        <div className="budget-cell">
          <div className="meter-head">
            <span className="eyebrow">Attention load</span>
            <b>
              {budget.load}/{budget.capacity}
            </b>
          </div>
          <div
            className={cls("meter", budget.over && "over", ratio >= 0.66 && !budget.over && "warn")}
            style={{ gridTemplateColumns: `repeat(${cap}, 1fr)` }}
            role="meter"
            aria-valuemin={0}
            aria-valuemax={budget.capacity}
            aria-valuenow={budget.load}
            aria-label="Operator attention load"
          >
            {Array.from({ length: cap }, (_, i) => (
              <i key={i} className={cls(i < budget.load && "on")} />
            ))}
          </div>
          <Spark trace={budget.trace} capacity={budget.capacity} />
          {budget.over && (
            <span style={{ fontSize: 12, color: "var(--r5)", fontWeight: 650 }}>Over budget · queue sorted by urgency</span>
          )}
        </div>
        <div className="budget-cell">
          <div className="meter-head">
            <span className="eyebrow">On sonar now · {budget.active}</span>
            <span className="muted" style={{ fontSize: 12 }}>
              {budget.seen} seen
            </span>
          </div>
          <div className="dist" aria-hidden>
            {RUNGS.map((r) =>
              budget.rung_counts[r] ? (
                <span key={r} style={{ width: `${(budget.rung_counts[r] / total) * 100}%`, background: rungVar(r) }} />
              ) : null,
            )}
          </div>
          <div className="dist-legend">
            {RUNGS.map((r) => (
              <span key={r} title={texts.rungs[r].name}>
                <i style={{ background: rungVar(r) }} />
                {texts.rungs[r].name} <b>{budget.rung_counts[r]}</b>
              </span>
            ))}
          </div>
        </div>
        <div className="budget-cell bang" title="A blunt system alarms on every detection">
          <span className="eyebrow">The bang vs. the ladder</span>
          <span>
            <s>{budget.bang} alarms</s>
          </span>
          <span>
            <b>
              {asks} ask{asks === 1 ? "" : "s"}
            </b>{" "}
            of a person
          </span>
        </div>
      </div>
    </section>
  );
}

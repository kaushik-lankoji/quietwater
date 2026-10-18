import type { OptimizationMetrics } from "../types";
import { Icon } from "./Icon";

const dollars = (amount: number) => "$" + amount.toLocaleString(undefined, { maximumFractionDigits: 2 });

function decisionTime(ms: number | null): string {
  if (ms === null) return "—";
  return ms < 1 ? "Under 1 ms" : ms.toFixed(1) + " ms";
}

export function OptimizationPanel({ metrics: m }: { metrics: OptimizationMetrics }) {
  const pauseSaved = Math.max(0, m.baseline_pause_operation_min - m.modeled_pause_operation_min);
  const hasHold = m.recommended_hold_radius_m !== null;
  return (
    <details className="optimization glass">
      <summary className="optimization-summary" aria-label={`Watch efficiency: ${dollars(m.cost_savings_usd)} in time and pause value freed. Open panel`}>
        <span className="optimization-compact" aria-hidden="true"><Icon name="receipt" size={23} /></span>
        <span className="optimization-summary-content">
          <strong>Watch efficiency</strong>
          <small>{m.traffic_level} · {m.coverage_radius_m.toLocaleString()} m radius</small>
        </span>
        <span className="optimization-chevron" aria-hidden="true">⌄</span>
      </summary>

      <div className="optimization-body">
        <div className="optimization-savings">
          <span className="optimization-kicker">Automation value</span>
          <strong>{dollars(m.cost_savings_usd)} freed</strong>
          <small>{m.cost_savings_pct}% below manual review + standard {m.baseline_hold_radius_m} m holds</small>
          <div className="optimization-value-breakdown">
            <span>Officer time <b>{dollars(m.officer_capacity_value_usd)}</b></span>
            <span>Paused work <b>{dollars(m.avoided_pause_cost_usd)}</b></span>
          </div>
          <div className="optimization-area-efficiency">
            <span><b>{m.savings_per_km2_usd === null ? "—" : dollars(m.savings_per_km2_usd)}</b><small>value freed per km²</small></span>
            <span><b>{m.cost_per_km2_usd === null ? "—" : dollars(m.cost_per_km2_usd)}</b><small>watch cost per km²</small></span>
          </div>
          <small>{m.coverage_km2.toFixed(2)} km² of water in this {m.coverage_radius_m.toLocaleString()} m watch radius</small>
        </div>
        <div className="optimization-cost">
          <span className="optimization-kicker">Estimated cost · {m.watch_horizon_min} min watch</span>
          <strong>{dollars(m.estimated_cost_usd)}</strong>
          <small>Manual-review benchmark: {dollars(m.baseline_cost_usd)}</small>
          <div><span>People <b>{dollars(m.staffing_cost_usd)}</b></span><span>Paused work <b>{dollars(m.pause_cost_usd)}</b></span><span>Cloud AI <b>{dollars(m.ai_cost_usd)}</b></span></div>
        </div>
        <div className="optimization-flow" aria-label={m.contacts_seen + " contacts seen, " + m.handled_quietly + " handled automatically, " + m.human_interruptions + " sent to an officer"}>
          <div><strong>{m.contacts_seen}</strong><span>seen</span></div>
          <span className="optimization-arrow" aria-hidden="true">→</span>
          <div className="optimization-quiet"><strong>{m.handled_quietly}</strong><span>handled quietly</span></div>
          <span className="optimization-arrow" aria-hidden="true">·</span>
          <div className="optimization-human"><strong>{m.human_interruptions}</strong><span>need a person</span></div>
        </div>

        <div className="optimization-takeaway">
          <span className="optimization-kicker">People</span>
          <strong>{m.recommended_operators === null ? "Review takes too long" : m.recommended_operators + " officer" + (m.recommended_operators === 1 ? "" : "s") + " needed"}</strong>
          <small>{m.current_operators} on watch · {m.officer_time_saved_min.toFixed(1)} min freed by automation</small>
          {m.recommended_operators !== null && (
            <span className="optimization-pill">{m.utilization_pct}% of this watch hour</span>
          )}
        </div>

        <div className="optimization-takeaway">
          <span className="optimization-kicker">Area holds</span>
          {hasHold ? (
            <>
              <strong>{m.recommended_hold_radius_m} m around the contact</strong>
              <small>Standard area: {m.baseline_hold_radius_m} m</small>
              <span className="optimization-pill">{pauseSaved.toFixed(1)} min of work kept running</span>
              <span className="optimization-pill">{dollars(m.avoided_pause_cost_usd)} estimated pause cost avoided</span>
            </>
          ) : (
            <strong>No area hold needed yet</strong>
          )}
        </div>

        <div className="optimization-takeaway optimization-compute">
          <span><strong>{m.llm_calls}</strong><small>cloud AI calls</small></span>
          <span><strong>{decisionTime(m.mean_decision_ms)}</strong><small>computer time per decision</small></span>
        </div>

        <p className="optimization-footnote">Demo baseline: {m.manual_triage_min_per_contact} min manual review per quiet contact, at {dollars(m.operator_hourly_usd)}/hour. Freed time is capacity value, not reduced payroll. Paused work uses {dollars(m.paused_operation_hourly_usd)}/hour. Holds need approval.</p>
      </div>
    </details>
  );
}

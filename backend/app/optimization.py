from __future__ import annotations

import heapq
import math
from typing import Any

from .geometry import distance_to
from .handoff import hold_options


def hold_radius(decision: dict[str, Any], rules: Any) -> float:
    position = tuple(decision["position"])
    at_risk = []
    focus_id = (decision.get("focus_asset") or {}).get("id")
    for asset in rules.assets:
        if not asset.active:
            continue
        distance = distance_to(position, asset.shape)
        band = rules.consequence.by_kind.get(asset.kind, rules.consequence.default)
        if distance <= band.high_m or asset.id == focus_id:
            at_risk.append(distance)
    minimum = max(at_risk, default=0) + rules.handoff.area_safety_buffer_m
    candidates = sorted(set(rules.handoff.area_radius_candidates_m))
    return next((r for r in candidates if r >= minimum), math.ceil(minimum / 50) * 50)


def _operators_for_windows(tasks: list[tuple[float, float, float]], horizon_min: float,
                           utilization: float) -> int | None:
    if not tasks:
        return 1
    work = sum(service for _, _, service in tasks)
    floor = max(1, math.ceil(work / (horizon_min * utilization)))
    for operators in range(floor, len(tasks) + 1):
        available = [0.0] * operators
        heapq.heapify(available)
        for arrival, deadline, service in sorted(tasks, key=lambda t: (t[0], t[1])):
            start = max(arrival, heapq.heappop(available))
            finish = start + service
            heapq.heappush(available, finish)
            if finish > deadline:
                break
        else:
            return operators
    return None


def metrics(session: Any, rules: Any, llm_calls: int = 0,
            decision_ms_total: float = 0, decision_count: int = 0) -> dict[str, Any]:
    cfg = rules.optimization
    radius = float(session.scenario.get("coverage_radius_m", 1000))
    tasks = []
    holds = []
    modeled_pause_min = 0.0
    baseline_pause_min = 0.0
    for contact_id, arrival_s in session.first_human_t.items():
        decision = session.peak.get(contact_id)
        if decision is None:
            continue
        service = cfg.handoff_review_min if "R5" in decision.rungs else cfg.hold_review_min
        deadline = (arrival_s + (decision.window_s or rules.windows_s.default)) / 60
        tasks.append((arrival_s / 60, deadline, service))
        if "R4" in decision.rungs:
            payload = decision.to_dict()
            optimized = hold_options(payload, rules, hold_radius(payload, rules))
            baseline = hold_options(payload, rules)
            if optimized and baseline:
                holds.append(optimized["radius_m"])
                for option, key in ((optimized, "optimized"), (baseline, "baseline")):
                    selected = next(o for o in option["options"] if o["scope"] == option["recommended"])
                    operation_minutes = len(selected["targets"]) * rules.handoff.hold_s / 60
                    if key == "optimized":
                        modeled_pause_min += operation_minutes
                    else:
                        baseline_pause_min += operation_minutes
    staff = _operators_for_windows(tasks, cfg.watch_horizon_min, cfg.target_utilization)
    work = sum(task[2] for task in tasks)
    human = len(session.first_human_t)
    seen = len(session.seen)
    staffing_usd = (staff or cfg.current_operators) * cfg.operator_hourly_usd * cfg.watch_horizon_min / 60
    pause_usd = modeled_pause_min * cfg.paused_operation_hourly_usd / 60
    baseline_pause_usd = baseline_pause_min * cfg.paused_operation_hourly_usd / 60
    ai_usd = llm_calls * cfg.llm_call_usd
    officer_time_saved_min = (seen - human) * cfg.manual_triage_min_per_contact
    officer_capacity_value_usd = officer_time_saved_min * cfg.operator_hourly_usd / 60
    coverage_km2 = session.scenario.get("water_area_km2", round(math.pi * (radius / 1000) ** 2, 2))
    estimated_cost_usd = staffing_usd + pause_usd + ai_usd
    avoided_pause_cost_usd = max(0, baseline_pause_usd - pause_usd)
    savings_usd = officer_capacity_value_usd + avoided_pause_cost_usd
    baseline_cost_usd = estimated_cost_usd + savings_usd
    return {
        "coverage_radius_m": radius,
        "coverage_km2": coverage_km2,
        "traffic_level": session.scenario.get("traffic_level", "Scripted"),
        "contacts_seen": seen,
        "handled_quietly": seen - human,
        "human_interruptions": human,
        "officer_minutes": round(work, 1),
        "officer_time_saved_min": round(officer_time_saved_min, 1),
        "officer_capacity_value_usd": round(officer_capacity_value_usd, 2),
        "manual_triage_min_per_contact": cfg.manual_triage_min_per_contact,
        "current_operators": cfg.current_operators,
        "recommended_operators": staff,
        "response_windows_feasible": staff is not None,
        "utilization_pct": round(100 * work / (cfg.current_operators * cfg.watch_horizon_min)),
        "watch_horizon_min": cfg.watch_horizon_min,
        "recommended_hold_radius_m": round(min(holds), 0) if holds else None,
        "baseline_hold_radius_m": rules.handoff.area_radius_m,
        "hold_radius_range_m": [round(min(holds)), round(max(holds))] if holds else None,
        "modeled_pause_operation_min": round(modeled_pause_min, 1),
        "baseline_pause_operation_min": round(baseline_pause_min, 1),
        "estimated_cost_usd": round(estimated_cost_usd, 2),
        "baseline_cost_usd": round(baseline_cost_usd, 2),
        "cost_savings_usd": round(savings_usd, 2),
        "cost_savings_pct": round(100 * savings_usd / baseline_cost_usd, 1) if baseline_cost_usd else 0,
        "cost_per_km2_usd": round(estimated_cost_usd / coverage_km2, 2) if coverage_km2 else None,
        "savings_per_km2_usd": round(savings_usd / coverage_km2, 2) if coverage_km2 else None,
        "staffing_cost_usd": round(staffing_usd, 2),
        "pause_cost_usd": round(pause_usd, 2),
        "ai_cost_usd": round(ai_usd, 2),
        "avoided_pause_cost_usd": round(avoided_pause_cost_usd, 2),
        "operator_hourly_usd": cfg.operator_hourly_usd,
        "paused_operation_hourly_usd": cfg.paused_operation_hourly_usd,
        "llm_calls": llm_calls,
        "mean_decision_ms": round(decision_ms_total / decision_count, 2) if decision_count else None,
        "decision_count": decision_count,
    }

from __future__ import annotations

from app.optimization import _operators_for_windows, hold_radius, metrics
from app.session import Session, World

from .conftest import REPO


def test_seed_controls_watch_radius_and_contact_area():
    world = World.load(REPO / "config")
    radii = {world.build("random_harbor", seed)["coverage_radius_m"] for seed in range(30)}
    assert len(radii) > 1
    assert world.build("random_harbor", 42) == world.build("random_harbor", 42)


def test_staffing_respects_response_windows_and_capacity():
    tasks = [(0, 5, 3), (0, 5, 3)]
    assert _operators_for_windows(tasks, 60, 0.7) == 2
    assert _operators_for_windows([(0, 30, 4)], 60, 0.7) == 1
    assert _operators_for_windows([(0, 2, 3)], 60, 0.7) is None


def test_hold_radius_covers_nearby_high_risk_assets(rules):
    decision = {"position": [1670, 245], "focus_asset": {"id": "fuel-dock-a"}}
    chosen = hold_radius(decision, rules)
    assert chosen in rules.handoff.area_radius_candidates_m
    assert chosen <= rules.handoff.area_radius_m


def test_metrics_expose_real_counts_and_no_default_llm_calls(rules):
    world = World.load(REPO / "config")
    session = Session(rules, world, "random_harbor", "security", 11)
    session.run(duration_s=90, dt=5)
    result = metrics(session, rules, session.llm_calls, session.decision_ms_total, session.decision_count)
    assert result["coverage_radius_m"] == session.scenario["coverage_radius_m"]
    assert result["contacts_seen"] == result["handled_quietly"] + result["human_interruptions"]
    assert result["recommended_operators"] >= 1
    assert result["llm_calls"] == 0
    assert result["mean_decision_ms"] is not None
    assert result["coverage_km2"] == session.scenario["water_area_km2"]
    assert result["estimated_cost_usd"] == round(
        result["staffing_cost_usd"] + result["pause_cost_usd"] + result["ai_cost_usd"], 2
    )
    assert result["avoided_pause_cost_usd"] >= 0
    assert result["officer_time_saved_min"] == (
        result["handled_quietly"] * rules.optimization.manual_triage_min_per_contact
    )
    assert result["cost_savings_usd"] == round(
        result["officer_capacity_value_usd"] + result["avoided_pause_cost_usd"], 2
    )
    assert result["baseline_cost_usd"] >= result["estimated_cost_usd"]
    assert result["savings_per_km2_usd"] == round(result["cost_savings_usd"] / result["coverage_km2"], 2)


def test_smaller_hold_reports_savings_per_covered_water_area(rules):
    world = World.load(REPO / "config")
    session = Session(rules, world, "random_harbor", "security", 0)
    session.run(duration_s=120, dt=5)
    result = metrics(session, rules)
    assert result["cost_savings_usd"] > 0
    assert result["cost_savings_pct"] > 0
    assert result["savings_per_km2_usd"] > 0


def test_automation_frees_officer_capacity_even_without_a_hold(rules):
    world = World.load(REPO / "config")
    world.catalog["scenarios"]["calm"] = {
        "title": "Calm", "mode": "security", "seed": 1, "duration_s": 120,
        "contacts": [{"id": "Q-1", "archetype": "bottle", "start": [720, 1000]},
                     {"id": "Q-2", "archetype": "fish", "start": [1300, 980], "heading": 200},
                     {"id": "Q-3", "archetype": "kelp", "start": [420, 720]}],
    }
    session = Session(rules, world, "calm", "security", 17)
    session.run(duration_s=120, dt=5)
    result = metrics(session, rules)
    assert result["contacts_seen"] > 0
    assert result["handled_quietly"] == result["contacts_seen"]
    assert result["avoided_pause_cost_usd"] == 0
    assert result["officer_capacity_value_usd"] == round(
        result["handled_quietly"] * rules.optimization.manual_triage_min_per_contact
        * rules.optimization.operator_hourly_usd / 60, 2
    )
    assert result["cost_savings_usd"] == result["officer_capacity_value_usd"]

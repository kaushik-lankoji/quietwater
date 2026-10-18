from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.engine import Memory, decide
from app.facts import AssetRef
from app.rules import RUNGS, parse_rules, plain, rung_index

from .conftest import asset, make_facts


def above(rules, key: str) -> float:
    return min(0.99, getattr(rules.thresholds, key) + 0.1)


def below(rules, key: str) -> float:
    return max(0.01, getattr(rules.thresholds, key) - 0.1)


def registered(rules, **kw):
    entry = rules.registry[0]
    zone = entry.authorized_zones[0]
    crit = next(z.critical for z in rules.zones if z.id == zone)
    base = dict(transponder=entry.id, registered=True, registry_id=entry.id, scheduled=True, zone_id=zone,
                zone_name=zone, zone_critical=crit, zone_authorized=True, label=entry.vehicle_type,
                confidence=above(rules, "classify_confidence"), hail="not_hailed", hail_age_s=None)
    base.update(kw)
    return make_facts(rules, **base)


def run(rules, f, mem=None, mode="security"):
    return decide(f, mem or Memory(), rules, mode)


def test_contact_routes_distinguish_no_link_from_ignored_hail(rules):
    unavailable = make_facts(rules, hail="unavailable", hail_route="unavailable", hail_age_s=None)
    memory = Memory()
    decision = run(rules, unavailable, memory)
    assert memory.hailed_t is None
    assert decision.hail == "unavailable"
    assert "no compatible vehicle link" in decision.why_lower.lower()
    assert "not answered the hail" not in decision.reason.lower()
    assert next(c for c in decision.checks if c["key"] == "hail")["ruled_out"] is None

    surface = run(rules, make_facts(rules, hail="none", hail_route="surface", consequence="medium"))
    assert rules.profile.surface_channel in surface.recommendation
    assert "support vessel or operator" in surface.recommendation


def test_human_approval_roles_follow_jurisdiction_profile(rules):
    high = run(rules, make_facts(rules, consequence="high", nearest_asset=asset(20)))
    assert high.requires_human
    assert high.approval_role == rules.profile.handoff_approver
    assert rules.profile.hold_approver in high.recommendation
    assert rules.profile.handoff_approver in high.recommendation


def test_s0_confident_non_vehicle_is_logged(rules):
    d = run(rules, make_facts(rules, label="biologic", confidence=above(rules, "non_vehicle_confidence")))
    assert d.path == ["S0"]
    assert d.rungs == rules.ladder.non_vehicle
    assert not d.requires_human


def test_s0_unsure_non_vehicle_goes_through_the_tree(rules):
    d = run(rules, make_facts(rules, label="biologic", confidence=below(rules, "non_vehicle_confidence")))
    assert d.path[0] == "S1"
    assert d.outcome == "unknown_low"


def test_s1_identity_ok_noncritical_watch(rules):
    d = run(rules, registered(rules, zone_critical=False))
    assert d.path == ["S1", "S3"]
    assert d.outcome == "identity_ok_noncritical"
    assert d.rungs == rules.ladder.identity_ok_noncritical
    assert d.notice is None


def test_s3_critical_zone_adds_informational_notice(rules):
    d = run(rules, registered(rules, zone_critical=True, zone_name="Main channel"))
    assert d.outcome == "identity_ok_critical"
    assert d.rungs == rules.ladder.identity_ok_critical
    assert d.notice and "Main channel" in d.notice


@pytest.mark.parametrize("field", ["registered", "scheduled", "zone_authorized"])
def test_s1_any_identity_gap_goes_to_hail(rules, field):
    kw = {field: False}
    if field == "registered":
        kw.update(registry_id=None, transponder=None)
    d = run(rules, registered(rules, hail="ok", **kw))
    assert d.path[:3] == ["S1", "S2", "S3"]
    assert d.rung == "R0"


@pytest.mark.parametrize("hail", ["none", "intermittent", "mismatch"])
def test_s2_no_good_answer_goes_to_s4(rules, hail):
    d = run(rules, make_facts(rules, hail=hail))
    assert d.path[:3] == ["S1", "S2", "S4"]


def test_s2_records_hail_time(rules):
    mem = Memory()
    run(rules, make_facts(rules, t=12.0), mem)
    assert mem.hailed_t == 12.0


def test_s3_inconsistent_goes_to_s4(rules):
    d = run(rules, registered(rules, consistent=False, consistency_note="size differs"))
    assert d.path[:3] == ["S1", "S3", "S4"]


@pytest.mark.parametrize("flags,needle", [
    ({"improvised": True, "label": "improvised_device", "confidence": 0.8}, "Improvised"),
    ({"hostile": True}, "hostile"),
    ({"approaching": AssetRef("fuel-dock-a", "Fuel Dock A", "fuel_dock", "fuel transfer", 120)}, "Closing on"),
])
def test_s4_threats_hand_off_urgently(rules, flags, needle):
    d = run(rules, make_facts(rules, **flags))
    assert d.path[-1] == "S4"
    assert d.outcome == "threat"
    assert d.rungs == rules.ladder.threat
    assert d.urgency == "urgent"
    assert d.requires_human
    assert d.window_s == rules.windows_s.urgent
    assert needle in d.reason


def test_s5_evasive_hands_off(rules):
    d = run(rules, make_facts(rules, evasive=True, evasion_note="turned 200° in 20 s after the hail"))
    assert d.outcome == "evasive"
    assert d.rungs == rules.ladder.evasive
    assert d.urgency == "urgent"


@pytest.mark.parametrize("label", ["research_auv", "commercial_rov"])
def test_s5_classifiable_goes_back_to_s3(rules, label):
    d = run(rules, make_facts(rules, label=label, confidence=above(rules, "classify_confidence")))
    assert d.path == ["S1", "S2", "S4", "S5", "S3"]
    assert d.rung == "R0"


def test_s5_back_to_s3_inconsistent_falls_to_unknown_without_looping(rules):
    d = run(rules, make_facts(rules, label="research_auv", confidence=above(rules, "classify_confidence"),
                              consistent=False, consistency_note="too fast for its class"))
    assert d.path == ["S1", "S2", "S4", "S5", "S3"]
    assert d.outcome == "unknown_low"
    assert "too fast" in d.reason


def test_s5_military_holds_and_hands_off_with_30_min_window(rules):
    d = run(rules, make_facts(rules, label="military_uuv", confidence=above(rules, "classify_confidence")))
    assert d.outcome == "military"
    assert d.rungs == rules.ladder.military
    assert d.window_s == rules.windows_s.hold_handoff
    assert d.requires_human


def test_unknown_low_watch_plus(rules):
    d = run(rules, make_facts(rules, consequence="low"))
    assert d.outcome == "unknown_low"
    assert d.rungs == rules.ladder.unknown_low
    assert not d.requires_human


def test_unknown_medium_without_traffic_asks(rules):
    d = run(rules, make_facts(rules, consequence="medium", nearest_asset=asset(200)))
    assert d.outcome == "unknown_medium_quiet"
    assert d.rungs == rules.ladder.unknown_medium_quiet


def test_unknown_medium_with_traffic_slows(rules):
    d = run(rules, make_facts(rules, consequence="medium", nearest_asset=asset(200), traffic=["Tug Bravo"]))
    assert d.outcome == "unknown_medium_traffic"
    assert d.rungs == rules.ladder.unknown_medium_traffic
    assert "Tug Bravo" in d.recommendation


def test_unknown_high_holds_one_operation_and_hands_off(rules):
    d = run(rules, make_facts(rules, consequence="high", nearest_asset=asset(60)))
    assert d.outcome == "unknown_high"
    assert d.rungs == rules.ladder.unknown_high
    assert d.requires_human
    assert d.window_s == rules.windows_s.hold_handoff
    assert "bunkering" in d.recommendation and "MT Sea Venture" in d.recommendation


def test_loop_cap_escalates_one_rung_and_never_loops_forever(rules):
    mem = Memory()
    interval, cap = rules.loop.interval_s, rules.loop.max_second_looks
    outcomes = []
    t = 0.0
    for _ in range(200):
        d = run(rules, make_facts(rules, t=t), mem)
        outcomes.append(d.outcome)
        t += interval / 3
    assert mem.second_looks == cap
    assert mem.escalated
    assert outcomes[-1] == "unknown_low_escalated"
    expected = [RUNGS[min(5, rung_index(r) + rules.loop.escalate_by)] for r in rules.ladder.unknown_low]
    assert d.rungs == sorted(set(expected), key=rung_index)
    first = outcomes.index("unknown_low_escalated")
    assert all(o == "unknown_low_escalated" for o in outcomes[first:])


def test_loop_cap_zero_escalates_immediately(rules):
    data = plain(rules.model_dump())
    data["loop"]["max_second_looks"] = 0
    d = run(parse_rules(data), make_facts(rules))
    assert d.outcome == "unknown_low_escalated"


def test_confidence_alone_never_escalates(rules):
    sure = run(rules, make_facts(rules, label="unknown", confidence=0.99, consequence="low"))
    unsure = run(rules, make_facts(rules, label="unknown", confidence=0.10, consequence="low"))
    assert sure.rungs == unsure.rungs == rules.ladder.unknown_low
    weak_military = run(rules, make_facts(rules, label="military_uuv", confidence=below(rules, "classify_confidence")))
    assert weak_military.outcome == "unknown_low"


def test_consequence_with_confidence_does_escalate(rules):
    low = run(rules, make_facts(rules, consequence="low"))
    high = run(rules, make_facts(rules, consequence="high", nearest_asset=asset(50)))
    assert rung_index(high.rung) > rung_index(low.rung)


def test_pending_hail_caps_escalation(rules):
    d = run(rules, make_facts(rules, hail="pending", hail_age_s=2, consequence="high", nearest_asset=asset(50)))
    assert d.outcome == "awaiting_hail"
    assert d.rungs == rules.ladder.awaiting_hail
    assert not d.requires_human


def test_pending_hail_does_not_delay_threats(rules):
    d = run(rules, make_facts(rules, hail="pending", hail_age_s=2, hostile=True))
    assert d.outcome == "threat"


def test_urgent_hand_off_latches(rules):
    mem = Memory()
    run(rules, make_facts(rules, evasive=True, evasion_note="turned"), mem)
    d = run(rules, make_facts(rules, t=5.0, evasive=False), mem)
    assert d.outcome == "evasive"
    assert d.t == 5.0


def test_automated_below_human_floor(rules):
    for rung in RUNGS:
        assert rules.requires_human(rung) == (rung_index(rung) >= rung_index(rules.human_required_from))
    assert rules.requires_human("R4") and rules.requires_human("R5")


def test_human_floor_cannot_be_raised_above_hold(rules):
    data = plain(rules.model_dump())
    data["human_required_from"] = "R5"
    with pytest.raises(ValidationError):
        parse_rules(data)


def test_every_decision_explains_itself(rules):
    cases = [
        make_facts(rules, label="biologic", confidence=0.95),
        registered(rules),
        make_facts(rules),
        make_facts(rules, consequence="medium", nearest_asset=asset(200)),
        make_facts(rules, consequence="high", nearest_asset=asset(50)),
        make_facts(rules, hostile=True),
    ]
    for f in cases:
        d = run(rules, f)
        assert d.reason and "\n" not in d.reason
        assert d.why_higher and d.why_lower
        assert isinstance(d.ruled_out, list)
        assert {c["key"] for c in d.checks} >= {"non_vehicle", "identity", "hail", "improvised", "evasive"}


def test_ruled_out_lists_cleared_hypotheses(rules):
    d = run(rules, make_facts(rules, consequence="high", nearest_asset=asset(50)))
    assert "Improvised device" in d.ruled_out
    assert "Answers the hail" in d.ruled_out
    assert "Near a critical asset" not in d.ruled_out


def lost(rules, **kw):
    entry = rules.registry_entry(rules.recovery.lost_vehicle_id)
    base = dict(signature=entry.signature, size_m=entry.size_m, label="research_auv",
                confidence=rules.recovery.confirm_confidence - 0.1)
    base.update(kw)
    return make_facts(rules, **base)


def test_recovery_possible_match_rescans_then_pings(rules):
    mem = Memory()
    t, outcomes = 0.0, []
    for _ in range(100):
        d = run(rules, lost(rules, t=t), mem, mode="recovery")
        outcomes.append(d.outcome)
        t += rules.loop.interval_s / 3
    assert outcomes[0] == "rec_possible"
    assert d.track == "recovery"
    assert outcomes[-1] == "rec_possible_exhausted"
    assert d.rungs == rules.recovery.ladder.possible_exhausted


def test_recovery_confirmed_hands_to_owner(rules):
    d = run(rules, lost(rules, confidence=0.95), mode="recovery")
    assert d.outcome == "rec_confirmed"
    assert d.rungs == rules.recovery.ladder.confirmed
    assert d.drift and "projected" in d.drift
    assert rules.modes["recovery"].handoff_target in d.recommendation


def test_recovery_confirmed_near_traffic_and_hazard(rules):
    d = run(rules, lost(rules, confidence=0.95, traffic=["Pilot boat 1"]), mode="recovery")
    assert d.outcome == "rec_confirmed_traffic"
    d = run(rules, lost(rules, confidence=0.95, consequence="high", nearest_asset=asset(40)), mode="recovery")
    assert d.outcome == "rec_confirmed_hazard"
    assert d.rungs == rules.recovery.ladder.confirmed_hazard


def test_recovery_mode_keeps_security_track_for_everything_else(rules):
    d = run(rules, make_facts(rules, consequence="high", nearest_asset=asset(50)), mode="recovery")
    assert d.track == "security"
    assert d.outcome == "unknown_high"
    d = run(rules, lost(rules, improvised=True, label="improvised_device", confidence=0.9), mode="recovery")
    assert d.track == "security" and d.outcome == "threat"


def test_recovery_ignores_other_identified_vehicles(rules):
    other = next(r for r in rules.registry if r.id != rules.recovery.lost_vehicle_id)
    d = run(rules, lost(rules, transponder=other.id), mode="recovery")
    assert d.track == "security"

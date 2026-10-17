from __future__ import annotations

import json
import random
import time

import pytest

from app.advisor import (
    FAIL_SAFE_REASON,
    HARD_OUTCOMES,
    Advice,
    AdvisorCache,
    AdvisorError,
    AdvisorLayer,
    LLMAdvisor,
    RuleBasedAdvisor,
    build_input,
    is_ambiguous,
    parse_advice,
    review,
)
from app.engine import Memory, decide
from app.rules import RUNGS, LLMCfg, rung_index

from .conftest import asset, make_facts


class Fixed:
    name = "stub"

    def __init__(self, advice=None, error: Exception | None = None, delay: float = 0.0):
        self.advice, self.error, self.delay, self.calls = advice, error, delay, 0

    def advise(self, x):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.advice


class Seeded:
    name = "seeded"

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def advise(self, x):
        return Advice(self.rng.randint(-5, 5), self.rng.random() < 0.3, "random suggestion", self.rng.random())


def layer(rules, primary=None, **cfg):
    return AdvisorLayer(rules.advisor.model_copy(update=cfg), "test", AdvisorCache(), primary)


def ambiguous_facts(rules, **kw):
    base = dict(label="unknown", confidence=0.3, hail="none", hail_age_s=30, consequence="medium",
                nearest_asset=asset(200), traffic=[], trend="closing",
                cpa={"asset": {"name": "MT Sea Venture"}, "distance_m": 150, "in_s": 60, "level": "medium"})
    base.update(kw)
    return make_facts(rules, **base)


def reviewed(rules, f, lay, mem=None, mode="security"):
    mem = mem or Memory()
    d = decide(f, mem, rules, mode)
    return d, review(f, mem, rules, mode, d, lay)


def random_facts(rules, rng: random.Random):
    label = rng.choice(["unknown", "biologic", "debris", "research_auv", "commercial_rov", "military_uuv",
                        "improvised_device"])
    level = rng.choice(["low", "medium", "high"])
    kw = dict(
        label=label, confidence=round(rng.random(), 2), hail=rng.choice(["none", "pending", "ok", "mismatch"]),
        hail_age_s=rng.uniform(0, 60), consequence=level,
        nearest_asset=asset(rng.choice([40, 150, 300, 900])), traffic=rng.choice([[], ["Tug Bravo"]]),
        size_m=rng.uniform(0.3, 4), speed_mps=rng.uniform(0, 3), consistent=rng.random() < 0.7,
        trend=rng.choice(["new", "closing", "leaving", "loitering", "steady"]),
        hostile=rng.random() < 0.05, evasive=rng.random() < 0.05, t=rng.uniform(0, 300),
    )
    if rng.random() < 0.1:
        kw["approaching"] = asset(100)
    return make_facts(rules, **kw)


def test_advisor_never_lowers_a_decision_property(rules):
    rng = random.Random(2024)
    for i in range(600):
        f = random_facts(rules, rng)
        mem = Memory(second_looks=rng.randint(0, 3), next_look_t=rng.choice([None, 0.0]))
        base_mem = Memory(**vars(mem))
        d = decide(f, base_mem, rules, "security")
        out = review(f, mem, rules, "security", decide(f, mem, rules, "security"), layer(rules, Seeded(i)))
        assert rung_index(out.rung) >= rung_index(d.rung), (i, d.outcome, out.outcome)
        assert out.severity() >= d.severity()
        assert set(map(rung_index, out.rungs)) and min(map(rung_index, out.rungs)) >= 0
        if out.requires_human:
            assert rung_index(out.rung) >= rung_index(rules.human_required_from)
        assert out.ai_raised_tier == rung_index(out.rung) - rung_index(d.rung) or out.ai_raised_tier == 0
        assert out.ai_raised_tier <= max(rules.advisor.max_raise, 1 + rules.loop.escalate_by)


@pytest.mark.parametrize("kw", [
    dict(improvised=True, label="improvised_device", confidence=0.9),
    dict(hostile=True),
    dict(approaching=asset(80)),
    dict(evasive=True, evasion_note="turned 150°"),
    dict(label="military_uuv", confidence=0.9),
    dict(consequence="high", nearest_asset=asset(50)),
])
def test_hard_triggers_are_never_sent_to_the_advisor_or_changed(rules, kw):
    stub = Fixed(Advice(-5, False, "lower it", 1.0))
    f = make_facts(rules, hail="none", hail_age_s=30, **kw)
    d, out = reviewed(rules, f, layer(rules, stub))
    assert d.outcome in HARD_OUTCOMES
    assert stub.calls == 0
    assert out.rungs == d.rungs and out.outcome == d.outcome and out.advisor is None


def test_identity_ok_and_confident_non_vehicles_are_not_ambiguous(rules):
    stub = Fixed(Advice(3, False, "raise", 1.0))
    fish = make_facts(rules, label="biologic", confidence=0.95, size_m=0.8, speed_mps=0.5)
    d, out = reviewed(rules, fish, layer(rules, stub))
    assert d.outcome == "non_vehicle" and not is_ambiguous(fish, d, rules)
    assert stub.calls == 0 and out.rungs == d.rungs


def test_negative_and_oversized_suggestions_are_clamped(rules):
    for raw, applied in ((-3, 0), (4, rules.advisor.max_raise)):
        f = ambiguous_facts(rules)
        d, out = reviewed(rules, f, layer(rules, Fixed(Advice(raw, False, "x", 0.9))))
        assert out.advisor["clamped"] is True
        assert out.advisor["suggestion"]["suggested_tier_raise"] == raw
        assert rung_index(out.rung) - rung_index(d.rung) == applied


def test_rule_based_advisor_raises_compounding_signals_and_records_it(rules):
    f = ambiguous_facts(rules)
    d, out = reviewed(rules, f, layer(rules))
    assert d.outcome == "unknown_medium_quiet"
    assert out.ai_raised_tier == 1 and rung_index(out.rung) == rung_index(d.rung) + 1
    assert out.ai_reason.startswith("Compounding signals") and "closing" in out.ai_reason
    assert out.advisor["source"] == "rule" and out.advisor["applied"] is True
    assert out.advisor["inputs"]["trend"] == "closing"
    assert out.path[-1] == "AI" and "Advisor:" in out.reason


def test_rule_based_advisor_leaves_quiet_contacts_alone(rules):
    f = ambiguous_facts(rules, trend="steady", consequence="low", nearest_asset=asset(900), cpa=None)
    d, out = reviewed(rules, f, layer(rules))
    assert out.rungs == d.rungs and out.ai_raised_tier == 0
    assert out.ambiguous and out.advisor["applied"] is False


def test_anomalous_non_vehicle_gets_a_capped_second_look(rules):
    mem = Memory()
    lay = layer(rules)
    outs = []
    t = 0.0
    for _ in range(60):
        f = make_facts(rules, label="biologic", confidence=0.9, size_m=3.4, speed_mps=0.4, t=t, hail="none")
        outs.append(review(f, mem, rules, "security", decide(f, mem, rules, "security"), lay))
        t += rules.loop.interval_s / 3
    assert outs[0].outcome == "advisor_second_look" and outs[0].rungs == ["R1"]
    assert mem.second_looks == rules.loop.max_second_looks
    assert outs[-1].outcome == "advisor_look_escalated" and outs[-1].rung == "R2"
    assert all(o.rung in ("R1", "R2") for o in outs)


@pytest.mark.parametrize("primary,needle", [
    (Fixed(error=RuntimeError("boom")), "boom"),
    (Fixed(Advice(1, False, "late", 1.0), delay=0.4), "timed out"),
    (LLMAdvisor(LLMCfg(), transport=lambda cfg, key, body: "Sure, I would raise it a lot!"), "no JSON"),
    (LLMAdvisor(LLMCfg(), transport=lambda cfg, key, body: '{"suggested_tier_raise": "two", "confidence": 2}'),
     "invalid advisor output"),
])
def test_advisor_failures_fall_back_to_rule_based(rules, primary, needle):
    f = ambiguous_facts(rules)
    lay = layer(rules, primary, timeout_s=0.1)
    d, out = reviewed(rules, f, lay)
    expected = RuleBasedAdvisor(rules.advisor).advise(build_input(f, d, rules))
    assert out.advisor["source"] == "rule_fallback"
    assert needle in out.advisor["error"]
    assert out.advisor["suggestion"]["reason"] == expected.reason
    assert rung_index(out.rung) >= rung_index(d.rung)


def test_missing_api_key_falls_back_without_network(rules, monkeypatch):
    monkeypatch.delenv(rules.advisor.llm.api_key_env, raising=False)
    lay = AdvisorLayer(rules.advisor.model_copy(update={"backend": "llm"}), "test", AdvisorCache())
    assert lay.primary.name == "llm"
    d, out = reviewed(rules, ambiguous_facts(rules), lay)
    assert out.advisor["source"] == "rule_fallback"
    assert "is not set" in out.advisor["error"]


def test_when_every_advisor_fails_the_contact_goes_up_one_rung(rules):
    lay = layer(rules, Fixed(error=RuntimeError("down")))
    lay.fallback = Fixed(error=RuntimeError("also down"))
    f = ambiguous_facts(rules, trend="steady", consequence="low", nearest_asset=asset(900), cpa=None)
    d, out = reviewed(rules, f, lay)
    assert out.advisor["source"] == "fail_safe"
    assert out.ai_reason == FAIL_SAFE_REASON
    assert rung_index(out.rung) == rung_index(d.rung) + 1
    assert "down" in out.advisor["error"] and "also down" in out.advisor["error"]


def test_valid_llm_json_is_parsed_strictly(rules):
    a = parse_advice('Here you go: {"suggested_tier_raise": 1, "second_look": false, '
                     '"reason": "silent and closing", "confidence": 0.8}')
    assert a == Advice(1, False, "silent and closing", 0.8)
    for bad in ('{"suggested_tier_raise": 1, "reason": "x", "confidence": 0.5, "extra": 1}',
                '{"suggested_tier_raise": 1, "reason": "two\\nlines", "confidence": 0.5}',
                '{"suggested_tier_raise": 1.5, "reason": "x", "confidence": 0.5}', "[]"):
        with pytest.raises(AdvisorError):
            parse_advice(bad)


def test_llm_answers_are_cached_per_snapshot_and_config(rules):
    calls = []

    def transport(cfg, key, body):
        calls.append(body)
        return json.dumps({"suggested_tier_raise": len(calls) % 2, "reason": "r", "confidence": 0.5})

    cache = AdvisorCache()
    lay = AdvisorLayer(rules.advisor, "hash-a", cache, LLMAdvisor(rules.advisor.llm, transport=transport))
    first = reviewed(rules, ambiguous_facts(rules), lay)[1]
    again = reviewed(rules, ambiguous_facts(rules, t=42.0), lay)[1]
    assert len(calls) == 1 and first.rungs == again.rungs
    other = AdvisorLayer(rules.advisor, "hash-b", cache, LLMAdvisor(rules.advisor.llm, transport=transport))
    reviewed(rules, ambiguous_facts(rules), other)
    assert len(calls) == 2


def test_llm_cache_persists_to_disk(rules, tmp_path):
    path = tmp_path / "cache.json"
    def transport(cfg, key, body):
        return '{"suggested_tier_raise": 1, "reason": "persisted", "confidence": 0.5}'

    lay = AdvisorLayer(rules.advisor, "h", AdvisorCache(path), LLMAdvisor(rules.advisor.llm, transport=transport))
    reviewed(rules, ambiguous_facts(rules), lay)
    assert path.exists()
    def offline(cfg, key, body):
        raise RuntimeError("no network")

    boom = LLMAdvisor(rules.advisor.llm, transport=offline)
    out = reviewed(rules, ambiguous_facts(rules), AdvisorLayer(rules.advisor, "h", AdvisorCache(path), boom))[1]
    assert out.advisor["source"] == "llm" and out.ai_reason == "persisted"


def test_disabled_advisor_changes_nothing(rules):
    off = rules.model_copy(update={"advisor": rules.advisor.model_copy(update={"enabled": False})})
    stub = Fixed(Advice(2, False, "x", 1.0))
    d, out = reviewed(off, ambiguous_facts(off), layer(off, stub))
    assert stub.calls == 0 and out is d


def test_recovery_track_can_be_raised_but_never_lowered(rules):
    entry = rules.registry_entry(rules.recovery.lost_vehicle_id)
    f = make_facts(rules, label="research_auv", confidence=0.6, signature=entry.signature, size_m=entry.size_m)
    d, out = reviewed(rules, f, layer(rules, Fixed(Advice(-2, True, "x", 0.5))), mode="recovery")
    assert d.track == "recovery" and d.outcome == "rec_possible"
    assert rung_index(out.rung) >= rung_index(d.rung)


def test_all_rungs_reachable_by_advisor_stay_within_ladder(rules):
    f = ambiguous_facts(rules)
    for raise_by in range(0, 6):
        d, out = reviewed(rules, f, layer(rules, Fixed(Advice(raise_by, False, "x", 1.0)), max_raise=5))
        assert out.rung in RUNGS

from __future__ import annotations

import random
import time

import pytest
from fastapi.testclient import TestClient

from app.advisor import Advice, AdvisorCache, AdvisorLayer
from app.classifier import Classification
from app.engine import decide
from app.facts import assess_trend, closest_approach, derive_facts
from app.main import create_app
from app.rules import apply_ops, parse_rules, plain
from app.session import Session, World
from app.twists import preview

from .conftest import REPO


@pytest.fixture()
def client(root):
    app = create_app(root, run_loop=False)
    with TestClient(app) as c:
        c.hub = app.state.hub
        yield c


@pytest.fixture(scope="module")
def world():
    return World.load(REPO / "config")


def advance(hub, seconds: float, dt: float = 1.0):
    for _ in range(int(seconds / dt)):
        hub._advance(dt)


def with_ops(rules, ops):
    return parse_rules(apply_ops(plain(rules.model_dump()), ops))


def track(points, heading, speed, t0=0.0, dt=1.0):
    return [(t0 + i * dt, x, y, heading if not callable(heading) else heading(i), speed)
            for i, (x, y) in enumerate(points)]


def facts_at(rules, x, y, heading, speed, trail, t, label="unknown", conf=0.4):
    return derive_facts(contact_id="X", t=t, clock="09:00:00", position=(x, y), heading=heading, speed_mps=speed,
                        size_m=1.4, signature="unclassified", transponder=None,
                        classification=Classification(label, conf), hail="none", hailed_t=0.0, hostile=False,
                        scripted_evasive=False, trail=trail, rules=rules)


def test_trend_detects_closing_leaving_loitering_and_new(rules):
    dock = next(a for a in rules.assets if a.id == "fuel-dock-a")
    ref = type("Ref", (), {"id": dock.id})()
    north = [(1700, 700 - 2 * i) for i in range(31)]
    assert assess_trend(rules, track(north, 0, 2), north[-1], 2, 30, ref)[0] == "closing"
    south = [(1700, 700 + 2 * i) for i in range(31)]
    assert assess_trend(rules, track(south, 180, 2), south[-1], 2, 30, ref)[0] == "leaving"
    circle = [(1700, 700)] * 31
    assert assess_trend(rules, track(circle, lambda i: i * 3 % 360, 0.2), circle[-1], 0.2, 30, ref)[0] == "loitering"
    assert assess_trend(rules, track(north[:5], 0, 2), north[4], 2, 4, ref)[0] == "new"


def test_cpa_raises_low_consequence_to_the_configured_cap(rules):
    north, south, start = 0, 180, (1700, 1120)
    cpa = closest_approach(rules, start, north, 2.0)
    assert cpa["asset"].id == "ti-cable" and cpa["level"] == "high" and cpa["in_s"] > 0
    f = facts_at(rules, *start, north, 2.0, [], 0.0)
    assert f.consequence == "medium" and f.consequence_basis == "cpa"
    away = facts_at(rules, *start, south, 2.0, [], 0.0)
    assert away.consequence == "low" and away.consequence_basis == "distance"
    capped = with_ops(rules, [{"path": "consequence.cpa.raise_to", "value": "high"}])
    assert facts_at(capped, *start, north, 2.0, [], 0.0).consequence == "high"
    off = with_ops(rules, [{"path": "consequence.cpa.horizon_s", "value": 0}])
    assert facts_at(off, *start, north, 2.0, [], 0.0).consequence == "low"
    fish = facts_at(rules, *start, north, 2.0, [], 0.0, label="biologic", conf=0.95)
    assert fish.cpa is None and fish.scan_label == "marine_life"


def test_scan_label_vocabulary(rules):
    def label(lbl, conf):
        return facts_at(rules, 900, 900, 0, 0.3, [], 0.0, label=lbl, conf=conf).scan_label
    assert label("debris", 0.9) == "debris"
    assert label("biologic", 0.9) == "marine_life"
    assert label("research_auv", 0.9) == "known_vehicle"
    assert label("research_auv", 0.4) == "unknown"
    assert label("military_uuv", 0.9) == "unknown"


def test_r4_r5_are_never_automated_and_need_operator_approval(client):
    hub = client.hub
    client.post("/api/sim/scenario", json={"name": "all_archetypes"})
    advance(hub, 90)
    assert all(not r["automated"] for r in hub.receipts if r["decision"]["rung"] in ("R4", "R5"))
    items = list(hub.items.values())
    assert items and all(i.status == "pending" and i.actor is None for i in items)
    item = items[0]
    assert client.post(f"/api/handoff/{item.id}", json={"action": "execute"}).status_code == 422
    assert client.post(f"/api/handoff/{item.id}", json={"action": "send"}).status_code == 409
    assert client.post("/api/handoff/H-999", json={"action": "approve"}).status_code == 404
    body = {"action": "approve", "operator": "Officer K", "scope": "operation"}
    ok = client.post(f"/api/handoff/{item.id}", json=body).json()
    assert ok["status"] == "hold_requesting" and ok["actor"] == "Officer K"
    approvals = [e for e in hub.audit if e["kind"] == "operator" and e["detail"]["action"] == "approve"]
    assert [e["actor"] for e in approvals] == ["Officer K"]


@pytest.mark.parametrize("name", ["harbor_morning", "all_archetypes", "lost_vehicle", "flood"])
def test_system_never_sends_an_alert_on_its_own(client, name):
    hub = client.hub
    client.post("/api/sim/scenario", json={"name": name})
    advance(hub, 300, dt=2.0)
    assert hub.outbox == [] and hub.hold_requests == []
    drafts = [i for i in hub.items.values() if i.draft]
    assert all(i.draft_status == "drafted" for i in drafts)
    assert not any("Sent alert" in e["reason"] for e in hub.audit)


def test_hot_reload_changes_live_decisions_and_twist_diff_matches_replays(client):
    hub = client.hub
    client.post("/api/sim/scenario", json={"name": "harbor_morning"})
    advance(hub, 60)
    assert hub.session.current["C-112"].rung == "R3"
    before_rules, before_hash = hub.store.rules, hub.session.advisor.config_hash
    path = hub.root / "config" / "rules.yaml"
    text = path.read_text()
    dock_b = "    operation: fuel transfer\n    active: {}"
    edited = text.replace(dock_b.format("false"), dock_b.format("true"))
    edited = edited.replace("name: West fuel berth\n    critical: false", "name: West fuel berth\n    critical: true")
    assert edited != text
    path.write_text(edited)
    hub.tick()
    assert hub.store.version == 2 and hub.session.advisor.config_hash != before_hash
    advance(hub, 12)
    live = hub.session.current["C-112"]
    assert live.requires_human and live.rungs == ["R4", "R5"] and "Fuel Dock B" in live.recommendation
    assert hub.receipts[-1]["config_hash"] == hub.session.advisor.config_hash

    seed = hub.session.seed
    impact = preview(before_rules, hub.store.rules, hub.world, "harbor_morning", "security", seed)
    row = next(r for r in impact["rows"] if r["contact_id"] == "C-112")
    assert row["before"]["rungs"] == ["R3"] and row["after"]["rungs"] == ["R4", "R5"] and row["direction"] == "up"
    for rules_, side in ((before_rules, "before"), (hub.store.rules, "after")):
        s = Session(rules_, hub.world, "harbor_morning", "security", seed)
        s.run(dt=1.0)
        assert impact[side]["need_you"] == sum(1 for d in s.peak.values() if d.requires_human)
    assert impact["before"]["need_you"] + 1 == impact["after"]["need_you"]


def test_same_seed_new_config_preview_is_repeatable(rules, world):
    after = with_ops(rules, [{"path": "thresholds.classify_confidence", "value": 0.85}])
    a = preview(rules, after, world, "random_harbor", "security", 99)
    b = preview(rules, after, world, "random_harbor", "security", 99)
    assert a == b


def test_contact_paths_scenario_only_hails_reachable_contacts(rules, world):
    session = Session(rules, world, "contact_paths")
    session.step(1)
    assert session.current["LINK-1"].hail == "unavailable"
    assert session.sim.active["LINK-1"].hailed_t is None
    assert session.current["LINK-2"].hail_route == "surface"
    assert session.sim.active["LINK-2"].hailed_t is not None


@pytest.mark.parametrize("profile,recipient,channel,lang", [
    ("la", "USCG Sector Los Angeles-Long Beach", "VHF 16", "en"),
    ("singapore", "MPA Port Operations Control Centre", "VHF 16 or 09", "en"),
    ("eu", "Kustwacht Nederland", "VHF 11", "nl"),
])
def test_jurisdiction_profiles_switch_by_config_only(client, profile, recipient, channel, lang):
    hub = client.hub
    r = client.post("/api/twist/apply", json={"ops": [{"path": "jurisdiction", "value": profile}], "title": profile})
    assert r.status_code == 200
    rules = hub.store.rules
    assert client.get("/api/health").json()["jurisdiction"] == profile
    assert rules.handoff_target("security") == recipient
    assert rules.handoff_target("recovery") == rules.modes["recovery"].handoff_target
    client.post("/api/sim/scenario", json={"name": "all_archetypes"})
    advance(hub, 90)
    asks = [r for r in hub.receipts if "R2" in r["decision"]["rungs"] and r["decision"]["track"] == "security"]
    assert asks and "acoustic" in asks[0]["decision"]["recommendation"]
    assert channel in rules.profile.surface_channel
    assert rules.profile.hold_approver and rules.profile.handoff_approver
    assert rules.profile.security_liaison
    item = next(i for i in hub.items.values() if i.draft)
    assert item.draft["to"] == recipient and item.draft["language"] == lang
    assert item.draft["body"].startswith(("AAN: " if lang == "nl" else "TO: ") + recipient)
    hold = next(i for i in hub.items.values() if i.decision["outcome"] == "unknown_high")
    assert hold.decision["window_s"] == rules.windows.hold_handoff
    remus = next(r for r in hub.receipts if r["contact_id"] == "A-3")["decision"]
    assert remus["registered"] is (profile == "la")
    if profile != "la":
        identity = next(c for c in remus["checks"] if c["key"] == "identity")
        assert rules.registry_source in identity["detail"]


def test_flood_is_fast_and_budget_adds_up(client):
    hub = client.hub
    client.post("/api/sim/scenario", json={"name": "flood"})
    started = time.perf_counter()
    advance(hub, 240, dt=1.0)
    elapsed = time.perf_counter() - started
    assert elapsed < 20, f"flood took {elapsed:.1f} s"
    b = hub.budget()
    assert b["total"] == b["seen"] == 200
    assert b["quiet"] + b["needed_operator"] == b["total"]
    item = next(iter(hub.items.values()))
    client.post(f"/api/handoff/{item.id}", json={"action": "approve", "scope": "operation"})
    b = hub.budget()
    assert b["quiet"] + b["needed_operator"] == b["total"]
    assert b["need_you"] <= b["needed_operator"]


def test_dual_use_runs_the_same_engine_with_recovery_wording(rules, world):
    s = Session(rules, world, "lost_vehicle", "recovery")
    s.run(dt=1.0)
    lost = s.peak["L-201"]
    assert lost.track == "recovery" and lost.path[0] == "M1"
    names = {r: rules.modes["recovery"].rungs[r].name for r in lost.rungs}
    assert lost.rung_names == [names[r] for r in lost.rungs]
    assert rules.modes["recovery"].handoff_target in lost.recommendation
    others = [d for cid, d in s.peak.items() if cid != "L-201"]
    assert others and all(d.track == "security" for d in others)
    fish = s.peak["L-203"]
    assert fish.rung_names == [rules.modes["recovery"].rungs["R0"].name]


class Noisy:
    name = "llm"

    def __init__(self):
        self.rng, self.calls = random.Random(), 0

    def advise(self, x):
        self.calls += 1
        return Advice(self.rng.randint(0, 2), self.rng.random() < 0.5, "noisy model", self.rng.random())


@pytest.mark.parametrize("name,mode,seed", [("harbor_morning", "security", None), ("random_harbor", "security", 5),
                                            ("random_recovery", "recovery", 5)])
def test_replay_is_deterministic_even_with_a_noisy_model(rules, world, name, mode, seed):
    cache = AdvisorCache()
    noisy = Noisy()

    def trace():
        lay = AdvisorLayer(rules.advisor, rules.config_hash(), cache, noisy)
        s = Session(rules, world, name, mode, seed, advisor=lay)
        return [(d.contact_id, d.t, tuple(d.rungs), d.outcome, d.ai_raised_tier) for _ in range(200)
                for d in s.step(1.0)]

    first = trace()
    calls = noisy.calls
    assert first == trace()
    assert noisy.calls == calls


def test_replay_with_rule_advisor_is_deterministic_through_the_api(client):
    hub = client.hub

    def run():
        client.post("/api/sim/scenario", json={"name": "random_harbor", "seed": 314})
        advance(hub, 120)
        return [(r["contact_id"], r["t"], tuple(r["decision"]["rungs"]), r["decision"]["ai_raised_tier"])
                for r in hub.receipts]

    assert run() == run()


def test_decide_is_pure_given_memory(rules):
    from app.engine import Memory

    from .conftest import make_facts
    f = make_facts(rules, consequence="medium", traffic=["Tug Bravo"])
    assert decide(f, Memory(), rules).to_dict() == decide(f, Memory(), rules).to_dict()

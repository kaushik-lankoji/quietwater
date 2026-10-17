from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.session import Session, World
from app.simulator import is_water

from .conftest import REPO

RANDOM = [("random_harbor", "security"), ("random_recovery", "recovery")]


@pytest.fixture(scope="module")
def world():
    return World.load(REPO / "config")


def tier(rung: str) -> str:
    return "high" if rung in ("R4", "R5") else "mid" if rung in ("R2", "R3") else "low"


@pytest.mark.parametrize("name,mode", RANDOM)
def test_same_seed_same_scenario_new_seed_new_scenario(world, name, mode):
    assert world.build(name, 4242) == world.build(name, 4242)
    assert world.build(name, 4242)["contacts"] != world.build(name, 4243)["contacts"]


@pytest.mark.parametrize("name,mode", RANDOM)
def test_contacts_are_valid(world, name, mode):
    for seed in range(60):
        scen = world.build(name, seed)
        contacts = scen["contacts"]
        assert 8 <= len(contacts) <= 15
        assert len({c["id"] for c in contacts}) == len(contacts)
        assert scen["seed"] == seed and scen["clock_start"]
        for c in contacts:
            assert c["archetype"] in world.catalog["archetypes"]
            assert is_water(world.harbor, tuple(c["start"]))
            for wp in c.get("waypoints", []):
                assert is_water(world.harbor, tuple(wp))


@pytest.mark.parametrize("name,mode", RANDOM)
def test_every_scenario_has_low_mid_and_high(rules, world, name, mode):
    for seed in range(25):
        s = Session(rules, world, name, mode, seed)
        s.run(dt=1.0)
        assert {tier(d.rung) for d in s.peak.values()} == {"low", "mid", "high"}, f"seed {seed}"


def test_recovery_scenario_contains_the_lost_vehicle(rules, world):
    sig = rules.registry_entry(rules.recovery.lost_vehicle_id).signature
    for seed in range(30):
        contacts = world.build("random_recovery", seed)["contacts"]
        assert sum(c.get("signature") == sig for c in contacts) == 1


@pytest.mark.parametrize("name,mode", RANDOM)
def test_random_runs_replay_identically(rules, world, name, mode):
    def trace():
        s = Session(rules, world, name, mode, 777)
        return [(d.contact_id, d.t, tuple(d.rungs), d.outcome) for _ in range(120) for d in s.step(1.0)]

    assert trace() == trace()


def test_generation_ignores_rules_so_twist_diffs_compare_like_with_like(rules, world):
    stricter = rules.model_copy(update={"thresholds": rules.thresholds.model_copy(update={"classify_confidence": 0.9})})
    a = Session(rules, world, "random_harbor", "security", 31)
    b = Session(stricter, world, "random_harbor", "security", 31)
    assert a.scenario["contacts"] == b.scenario["contacts"]


def test_api_loads_seeded_random_scenario_and_replay_keeps_the_seed(root):
    app = create_app(root, run_loop=False)
    with TestClient(app) as client:
        hub = app.state.hub
        body = client.post("/api/sim/scenario", json={"name": "random_harbor", "seed": 9001}).json()
        assert body == {"scenario": "random_harbor", "seed": 9001, "mode": "security"}
        first = [c["id"] + str(c["start"]) for c in hub.session.scenario["contacts"]]
        client.post("/api/sim/control", json={"action": "restart"})
        assert hub.session.seed == 9001
        assert [c["id"] + str(c["start"]) for c in hub.session.scenario["contacts"]] == first
        state = client.get("/api/state").json()
        assert state["scenario"]["seed"] == 9001
        assert state["scenario"]["description"].startswith("Seed 9001")
        client.post("/api/sim/scenario", json={"name": "random_recovery", "seed": 5})
        assert hub.mode == "recovery"
        scenarios = {s["id"]: s for s in client.get("/api/config").json()["scenarios"]}
        assert scenarios["random_harbor"]["random"] and not scenarios["harbor_morning"]["random"]

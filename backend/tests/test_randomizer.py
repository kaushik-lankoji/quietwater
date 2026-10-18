from __future__ import annotations

import math

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
        assert 0 <= len(contacts) <= 200
        assert 350 <= scen["coverage_radius_m"] <= 1300
        assert scen["water_area_km2"] > 0
        assert len({c["id"] for c in contacts}) == len(contacts)
        assert scen["seed"] == seed and scen["clock_start"]
        for c in contacts:
            assert c["archetype"] in world.catalog["archetypes"]
            assert is_water(world.harbor, tuple(c["start"]))
            center = world.harbor["sensor_center"]
            assert math.dist(c["start"], (center["x"], center["y"])) <= scen["coverage_radius_m"]
            for wp in c.get("waypoints", []):
                assert is_water(world.harbor, tuple(wp))
                assert math.dist(wp, (center["x"], center["y"])) <= scen["coverage_radius_m"]


@pytest.mark.parametrize("name,mode", RANDOM)
def test_traffic_ranges_include_clear_and_peak_even_at_different_radii(world, name, mode):
    scenarios = [world.build(name, seed) for seed in range(100)]
    assert any(len(s["contacts"]) <= 3 for s in scenarios)
    assert any(len(s["contacts"]) >= 81 for s in scenarios)
    assert len({s["coverage_radius_m"] for s in scenarios}) >= 10
    assert any(s["traffic_level"] == "Peak surge" and s["coverage_radius_m"] < 800 for s in scenarios)


def test_recovery_scenario_contains_the_lost_vehicle(rules, world):
    sig = rules.registry_entry(rules.recovery.lost_vehicle_id).signature
    for seed in range(30):
        scenario = world.build("random_recovery", seed)
        contacts = scenario["contacts"]
        assert sum(c.get("signature") == sig for c in contacts) <= 1
        if len(contacts) >= 3 and scenario["coverage_radius_m"] >= 800:
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


@pytest.mark.parametrize("name", ["harbor_morning", "lost_vehicle", "flood", "all_archetypes"])
def test_generate_keeps_the_selected_scenario_and_only_varies_details(world, name):
    base = world.build(name)
    a, b = world.build(name, 101), world.build(name, 202)
    assert world.build(name, 101) == a
    assert a != b and a["seed"] == 101
    for new in (a, b):
        assert new["title"] == base["title"] and new["mode"] == base["mode"]
        roster = lambda sc: [(c["id"], c["archetype"]) for c in sc["contacts"]]  # noqa: E731
        assert roster(new) == roster(base)
        assert new.get("generator") == base.get("generator")
        for c in new["contacts"]:
            assert is_water(world.harbor, tuple(c["start"]))
            assert all(is_water(world.harbor, tuple(p)) for p in c.get("waypoints", []))


def test_unseeded_scenario_is_unchanged(world):
    assert world.build("harbor_morning") is world.scenario("harbor_morning")


@pytest.mark.parametrize("seed", range(1, 13))
def test_morning_watch_story_survives_a_new_seed(rules, world, seed):
    s = Session(rules, world, "harbor_morning", "security", seed)
    s.run()
    assert {cid: s.peak[cid].rung for cid in ("C-107", "C-108")} == {"C-107": "R5", "C-108": "R5"}


@pytest.mark.parametrize("seed", range(1, 41))
def test_every_random_harbor_has_a_red_contact_early(rules, world, seed):
    s = Session(rules, world, "random_harbor", "security", seed)
    first = None
    while s.sim.t < 60 and first is None:
        if any(d.rung in ("R4", "R5") for d in s.step(1.0)):
            first = s.sim.t
    assert first is not None and first <= 40

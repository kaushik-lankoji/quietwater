from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.classifier import MockClassifier, Observation
from app.facts import assess_consequence, detect_evasion, find_approach, in_window, resolve_zone
from app.geometry import distance_to
from app.rules import Shape, apply_ops, field_diff, parse_rules, plain
from app.session import Session, World

from .conftest import REPO


def test_shapes_distance():
    rect = Shape(type="rect", x=0, y=0, w=10, h=10)
    assert distance_to((5, 5), rect) == 0
    assert distance_to((13, 14), rect) == pytest.approx(5)
    circle = Shape(type="circle", x=0, y=0, r=5)
    assert distance_to((10, 0), circle) == pytest.approx(5)
    line = Shape(type="line", points=[(0, 0), (100, 0)], width=10)
    assert distance_to((50, 25), line) == pytest.approx(20)


def test_schedule_windows_including_overnight():
    assert in_window("09:00:00", "08:00", "16:00")
    assert not in_window("16:00:00", "08:00", "16:00")
    assert in_window("23:30:00", "22:00", "02:00")
    assert in_window("01:00:00", "22:00", "02:00")


def test_zone_and_consequence_from_config(rules):
    zone = resolve_zone(rules, (500, 1000))
    assert zone is not None and zone.id == "research_box"
    dock = next(a for a in rules.assets if a.kind == "fuel_dock" and a.active)
    x, y = dock.shape.x + dock.shape.w / 2, dock.shape.y + dock.shape.h + 10
    level, ref = assess_consequence(rules, (x, y))
    assert level == "high" and ref.kind in ("fuel_dock", "ship")


def test_inactive_assets_carry_no_consequence(rules):
    data = plain(rules.model_dump())
    for a in data["assets"]:
        a["active"] = False
    off = parse_rules(data)
    level, _ = assess_consequence(off, (1700, 300))
    assert level == "low"


def test_approach_needs_speed_and_heading(rules):
    dock = next(a for a in rules.assets if a.id == "fuel-dock-a")
    p = (dock.shape.x + 50, dock.shape.y + dock.shape.h + 150)
    fast = rules.approach.min_speed_mps + 0.5
    assert find_approach(rules, p, 0, fast) is not None
    assert find_approach(rules, p, 180, fast) is None
    assert find_approach(rules, p, 0, rules.approach.min_speed_mps / 2) is None


def test_evasion_detection(rules):
    trail = [(t, 0, 0, (t * 30) % 360, 1.0) for t in range(0, 30)]
    evasive, note = detect_evasion(rules, trail, hailed_t=5, now=29)
    assert evasive and "turned" in note
    steady = [(t, 0, 0, 90, 1.0) for t in range(0, 30)]
    assert detect_evasion(rules, steady, hailed_t=5, now=29) == (False, "")
    assert detect_evasion(rules, trail, hailed_t=None, now=29) == (False, "")


def test_mock_classifier_is_deterministic_and_improves_with_looks():
    clf = MockClassifier({"base": {"research_auv": 0.5}, "per_look": 0.1, "noise": 0.0})
    obs = dict(contact_id="X", t=0, age_s=0, size_m=1.5, speed_mps=1, signature="s", truth="research_auv")
    a = clf.classify(Observation(look=0, **obs))
    b = clf.classify(Observation(look=2, **obs))
    assert b.confidence > a.confidence
    assert clf.classify(Observation(look=0, **obs)) == a


def test_label_track_by_look_overrides_truth():
    clf = MockClassifier({})
    track = ({"look": 0, "label": "unknown", "conf": 0.4}, {"look": 1, "label": "biologic", "conf": 0.9})
    obs = dict(contact_id="X", t=0, age_s=0, size_m=1, speed_mps=1, signature="s", label_track=track)
    assert clf.classify(Observation(look=0, **obs)).label == "unknown"
    assert clf.classify(Observation(look=1, **obs)).label == "biologic"


def test_apply_ops_set_append_remove(rules):
    data = plain(rules.model_dump())
    out = apply_ops(data, [
        {"path": "thresholds.classify_confidence", "value": 0.9},
        {"path": "assets[fuel-dock-b].active", "value": True},
        {"op": "append", "path": "traffic", "value": {"id": "x", "name": "X", "x": 1, "y": 1}},
        {"op": "remove", "path": "traffic[tug-bravo]"},
    ])
    parsed = parse_rules(out)
    assert parsed.thresholds.classify_confidence == 0.9
    assert next(a for a in parsed.assets if a.id == "fuel-dock-b").active
    assert {v.id for v in parsed.traffic} >= {"x"} and "tug-bravo" not in {v.id for v in parsed.traffic}
    paths = {c["path"] for c in field_diff(data, out)}
    assert "thresholds.classify_confidence" in paths
    assert "assets[fuel-dock-b].active" in paths
    assert data["thresholds"]["classify_confidence"] != 0.9


def test_bad_twists_are_rejected(rules):
    data = plain(rules.model_dump())
    with pytest.raises(KeyError):
        apply_ops(data, [{"path": "zones[nope].critical", "value": True}])
    bad = apply_ops(data, [{"path": "registry[USC-REMUS-01].authorized_zones", "value": ["atlantis"]}])
    with pytest.raises(ValidationError):
        parse_rules(bad)
    bad = apply_ops(data, [{"path": "thresholds.classify_confidence", "value": 3}])
    with pytest.raises(ValidationError):
        parse_rules(bad)


def test_presets_all_validate(rules):
    world = World.load(REPO / "config")
    data = plain(rules.model_dump())
    for preset in world.presets:
        parse_rules(apply_ops(data, preset["ops"]))


@pytest.mark.parametrize("name", ["harbor_morning", "all_archetypes", "lost_vehicle"])
def test_scenarios_are_deterministic(rules, name):
    world = World.load(REPO / "config")
    mode = world.scenario(name).get("mode", "security")

    def trace():
        s = Session(rules, world, name, mode)
        out = []
        for _ in range(120):
            out += [(d.contact_id, d.t, tuple(d.rungs), d.outcome) for d in s.step(1.0)]
        return out

    assert trace() == trace()


def test_flood_keeps_the_queue_short(rules):
    world = World.load(REPO / "config")
    s = Session(rules, world, "flood", "security")
    s.run(dt=2.0)
    assert len(s.seen) == 200
    assert len(s.first_human_t) <= 10


def test_every_archetype_reaches_a_decision(rules):
    world = World.load(REPO / "config")
    s = Session(rules, world, "all_archetypes", "security")
    s.run(dt=1.0)
    assert set(s.seen) == {c["id"] for c in world.scenario("all_archetypes")["contacts"]}
    assert all(s.peak[c].reason for c in s.seen)

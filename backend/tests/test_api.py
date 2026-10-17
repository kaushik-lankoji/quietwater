from __future__ import annotations

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(root):
    app = create_app(root, run_loop=False)
    with TestClient(app) as c:
        c.hub = app.state.hub
        yield c


def advance(hub, seconds: float, dt: float = 1.0):
    for _ in range(int(seconds / dt)):
        hub._advance(dt)


def test_health_and_config(client):
    assert client.get("/api/health").json()["ok"]
    cfg = client.get("/api/config").json()
    assert {"harbor", "rules", "scenarios", "presets"} <= cfg.keys()
    assert any(s["id"] == "flood" for s in cfg["scenarios"])


def test_state_snapshot_has_budget_and_contacts(client):
    advance(client.hub, 5)
    state = client.get("/api/state").json()
    assert state["contacts"]
    assert {"quiet", "need_you", "load", "capacity", "bang"} <= state["budget"].keys()
    assert state["receipts"]


def test_handoff_approve_then_send_draft(client):
    hub = client.hub
    client.post("/api/sim/scenario", json={"name": "all_archetypes"})
    advance(hub, 30)
    items = [i for i in hub.items.values() if i.status == "pending"]
    assert items
    r5 = next(i for i in items if "R5" in i.decision["rungs"])
    assert r5.draft and "TO:" in r5.draft["body"]
    assert client.post(f"/api/handoff/{r5.id}", json={"action": "send"}).status_code == 409
    approved = client.post(f"/api/handoff/{r5.id}", json={"action": "approve", "operator": "Test"}).json()
    assert approved["status"] == "approved"
    sent = client.post(f"/api/handoff/{r5.id}", json={"action": "send", "operator": "Test"}).json()
    assert sent["draft_status"] == "sent"
    assert client.post(f"/api/handoff/{r5.id}", json={"action": "reject"}).status_code == 409


def test_keep_watching_snoozes_then_returns(client):
    hub = client.hub
    client.post("/api/sim/scenario", json={"name": "all_archetypes"})
    advance(hub, 30)
    item = next(i for i in hub.items.values() if i.status == "pending")
    client.post(f"/api/handoff/{item.id}", json={"action": "watch"})
    assert hub.items[item.id].status == "watching"
    advance(hub, hub.store.rules.alert_budget.keep_watching_snooze_s + 2)
    assert hub.items[item.id].status in ("pending", "stood_down")


def test_budget_counts_quiet_vs_need_you(client):
    hub = client.hub
    client.post("/api/sim/scenario", json={"name": "flood"})
    advance(hub, 120, dt=2.0)
    b = hub.budget()
    assert b["seen"] == 200
    assert b["quiet"] >= 190
    assert b["need_you"] <= 10
    assert b["bang"] == 200


def test_twist_preview_apply_history_revert(client):
    hub = client.hub
    ops = [{"path": "assets[fuel-dock-b].active", "value": True},
           {"path": "consequence.by_kind.fuel_dock.high_m", "value": 900},
           {"path": "consequence.by_kind.fuel_dock.medium_m", "value": 1200}]
    prev = client.post("/api/twist/preview", json={"ops": ops}).json()
    assert {c["path"] for c in prev["changes"]} >= {"assets[fuel-dock-b].active"}
    assert prev["impact"]["changed"] > 0
    assert prev["impact"]["after"]["need_you"] > prev["impact"]["before"]["need_you"]
    v = hub.store.version
    entry = client.post("/api/twist/apply", json={"ops": ops, "title": "Dock B", "note": "test"}).json()
    assert hub.store.version == v + 1
    assert entry["impact"]["changed"] > 0
    assert "fuel-dock-b" in (hub.root / "config" / "rules.yaml").read_text()
    assert hub.store.rules.consequence.by_kind["fuel_dock"].high_m == 900
    history = client.get("/api/twist/history").json()
    assert history[0]["id"] == entry["id"]
    client.post(f"/api/twist/revert/{entry['id']}")
    assert hub.store.rules.consequence.by_kind["fuel_dock"].high_m != 900
    assert json.loads((hub.root / "data" / "twist_history.json").read_text())[-1]["source"] == "revert"


def test_apply_preserves_yaml_comments(client):
    hub = client.hub
    client.post("/api/twist/apply", json={"ops": [{"path": "loop.max_second_looks", "value": 3}]})
    text = (hub.root / "config" / "rules.yaml").read_text()
    assert text.startswith("# Quietwater rules.")
    assert "max_second_looks: 3" in text


def test_invalid_twist_is_rejected_and_rules_unchanged(client):
    hub = client.hub
    v = hub.store.version
    r = client.post("/api/twist/apply", json={"ops": [{"path": "human_required_from", "value": "R5"}]})
    assert r.status_code == 422
    assert "R4" in r.json()["detail"]
    assert hub.store.version == v
    r = client.post("/api/twist/preview", json={"yaml": "harbor: [unclosed"})
    assert r.status_code == 422


def test_file_edit_hot_reloads_and_bad_edit_keeps_last_good(client):
    hub = client.hub
    path = hub.root / "config" / "rules.yaml"
    text = path.read_text()
    path.write_text(text.replace("classify_confidence: 0.70", "classify_confidence: 0.80"))
    hub.tick()
    assert hub.store.rules.thresholds.classify_confidence == 0.80
    assert hub.history.entries[-1]["source"] == "file"
    path.write_text("thresholds: [broken")
    hub.tick()
    assert hub.store.error
    assert hub.store.rules.thresholds.classify_confidence == 0.80


def test_mode_switch_loads_recovery(client):
    r = client.post("/api/mode", json={"mode": "recovery"}).json()
    assert r == {"mode": "recovery", "scenario": "lost_vehicle"}
    advance(client.hub, 40)
    items = list(client.hub.items.values())
    assert any(i.decision["track"] == "recovery" for i in items)
    item = next(i for i in items if i.decision["track"] == "recovery")
    assert "Wrigley" in item.draft["to"]


def test_audit_export_json_and_csv(client):
    advance(client.hub, 10)
    data = client.get("/api/audit/export?format=json").json()
    assert data["entries"] and data["entries"][0]["kind"] == "scenario"
    r = client.get("/api/audit/export?format=csv")
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:4] == ["seq", "wall_time", "sim_clock", "mode"]
    assert len(rows) > 2


def test_sim_controls(client):
    assert client.post("/api/sim/control", json={"action": "pause"}).json()["running"] is False
    assert client.post("/api/sim/control", json={"action": "speed", "speed": 4.2}).json()["speed"] == 5
    client.post("/api/sim/control", json={"action": "restart"})
    assert client.hub.session.t == 0

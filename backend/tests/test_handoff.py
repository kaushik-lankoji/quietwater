"""Hand-off states: every legal move, every illegal one, and what each move leaves behind."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import handoff as hs
from app.main import create_app


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def client(root):
    app = create_app(root, run_loop=False)
    with TestClient(app) as c:
        hub = app.state.hub
        hub.wall = Clock()
        c.hub = hub
        c.post("/api/sim/scenario", json={"name": "all_archetypes"})
        advance(hub, 30)
        yield c


def advance(hub, seconds: float, dt: float = 1.0):
    for _ in range(int(seconds / dt)):
        hub._advance(dt)


def hold_item(hub):
    return next(i for i in hub.items.values() if i.decision["rungs"] == ["R4", "R5"] and i.status == "pending")


def notice_only_item(hub):
    return next(i for i in hub.items.values() if i.decision["rungs"] == ["R5"] and i.status == "pending")


def act(client, item, action, **body):
    if action in ("approve", "retry") and "scope" not in body:
        body["scope"] = "operation"
    return client.post(f"/api/handoff/{item.id}", json={"action": action, "operator": "Officer K", **body})


def ok(client, item, action, **body):
    r = act(client, item, action, **body)
    assert r.status_code == 200, r.json()
    return r.json()


def settle(client, seconds: float = 1.0):
    client.hub.wall.now += seconds
    client.hub.tick()


def last_receipt(hub):
    return hub.receipts[-1]


# --- the hold path ---------------------------------------------------------------------------------------------


def test_approve_requests_a_mock_hold_and_never_the_notice(client):
    hub = client.hub
    item = hold_item(hub)
    before = hub.budget()["need_you"]
    out = ok(client, item, "approve")
    assert out["status"] == "hold_requesting"
    assert [r["asset"] for r in hub.hold_requests] == [item.hold["asset"]]
    assert hub.hold_requests[0]["requested_by"] == "Officer K" and hub.hold_requests[0]["mock"]
    assert hub.outbox == [] and item.draft_status == "drafted"
    assert hub.budget()["need_you"] == before - 1
    rec = last_receipt(hub)
    assert rec["kind"] == "handoff" and rec["transition"]["from"] == "pending"
    assert rec["transition"]["to"] == "hold_requesting" and rec["automated"] is False


def test_hold_confirms_after_about_a_second(client):
    hub = client.hub
    item = hold_item(hub)
    ok(client, item, "approve")
    settle(client, 0.4)
    assert item.status == "hold_requesting"
    settle(client, 0.7)
    assert item.status == "hold_active" and item.hold["status"] == "active"
    left = item.to_dict(hub.session.t)["hold_left_s"]
    assert left == pytest.approx(hub.store.rules.handoff.hold_s, abs=1)
    assert hub.budget()["holds"] == 1
    assert last_receipt(hub)["transition"] | {"label": None} == {
        "item": item.id, "action": "hold_confirmed", "from": "hold_requesting", "to": "hold_active",
        "actor": "system", "label": None}


def test_hold_failure_then_retry(client):
    hub = client.hub
    hub.mock_hold_fail = True
    item = hold_item(hub)
    ok(client, item, "approve")
    settle(client)
    assert item.status == "hold_failed" and hub.hold_requests[0]["result"] == "failed"
    assert hub.budget()["holds"] == 0
    hub.mock_hold_fail = False
    assert ok(client, item, "retry")["status"] == "hold_requesting"
    settle(client)
    assert item.status == "hold_active" and len(hub.hold_requests) == 2


def test_failed_hold_can_still_go_to_notice_review_and_back(client):
    hub = client.hub
    hub.mock_hold_fail = True
    item = hold_item(hub)
    ok(client, item, "approve")
    settle(client)
    assert ok(client, item, "review")["status"] == "notice_review"
    assert ok(client, item, "cancel")["status"] == "hold_failed"


def test_full_path_hold_review_edit_send_lift(client):
    hub = client.hub
    item = hold_item(hub)
    ok(client, item, "approve")
    settle(client)
    assert ok(client, item, "review")["status"] == "notice_review"
    edited = ok(client, item, "edit", body="TO: USCG\nEdited by the officer.")
    assert edited["status"] == "notice_review" and edited["draft"]["body"].endswith("officer.")
    advance(hub, 5)
    assert item.draft["body"].endswith("officer."), "an edited draft is never regenerated"
    assert ok(client, item, "cancel")["status"] == "hold_active"
    ok(client, item, "review")
    assert act(client, item, "send").status_code == 409, "send needs an explicit confirm"
    assert hub.outbox == []
    sent = ok(client, item, "send", confirm=True)
    assert sent["status"] == "notice_sent" and sent["draft_status"] == "sent"
    assert len(hub.outbox) == 1 and hub.outbox[0]["by"] == "Officer K"
    assert hub.outbox[0]["body"].endswith("officer.")
    assert hub.budget()["notices_sent"] == 1
    assert act(client, item, "review").status_code == 409, "no Undo after send"
    lifted = ok(client, item, "lift")
    assert lifted["status"] == "lifted" and lifted["hold"]["status"] == "lifted"
    assert lifted["resolved_clock"]
    assert len(hub.outbox) == 1


def test_an_active_hold_can_only_end_by_lifting_it(client):
    hub = client.hub
    item = hold_item(hub)
    ok(client, item, "approve")
    settle(client)
    assert act(client, item, "resolve").status_code == 409
    ok(client, item, "review")
    ok(client, item, "send", confirm=True)
    r = act(client, item, "resolve")
    assert r.status_code == 409 and "lift the hold" in r.json()["detail"]
    assert ok(client, item, "lift")["status"] == "lifted"
    assert hub.budget()["holds"] == 0


def test_failed_hold_can_be_closed_as_resolved(client):
    hub = client.hub
    hub.mock_hold_fail = True
    item = hold_item(hub)
    ok(client, item, "approve")
    settle(client)
    assert ok(client, item, "resolve")["status"] == "resolved"
    assert hub.outbox == [] and hub.budget()["holds"] == 0


def test_hold_timer_ends_but_the_hold_stays_until_lifted_or_extended(client):
    hub = client.hub
    item = hold_item(hub)
    ok(client, item, "approve")
    settle(client)
    advance(hub, hub.store.rules.handoff.hold_s + 5, dt=5.0)
    assert item.status == "hold_active" and item.hold["time_up"]
    assert item.to_dict(hub.session.t)["hold_left_s"] <= 0
    ext = ok(client, item, "extend")
    assert ext["hold_left_s"] == pytest.approx(hub.store.rules.handoff.hold_s, abs=1)
    assert not item.hold["time_up"]


def test_lift_and_extend_need_an_active_hold(client):
    hub = client.hub
    item = notice_only_item(hub)
    ok(client, item, "review")
    ok(client, item, "send", confirm=True)
    assert act(client, item, "lift").status_code == 409
    assert act(client, item, "extend").status_code == 409
    assert ok(client, item, "resolve")["status"] == "resolved"


# --- notice-only items -----------------------------------------------------------------------------------------


def test_notice_only_item_has_nothing_to_approve(client):
    hub = client.hub
    item = notice_only_item(hub)
    plan = item.to_dict(hub.session.t)["plan"]
    assert [p["kind"] for p in plan] == ["notice"]
    assert act(client, item, "approve").status_code == 409
    assert item.status == "pending" and hub.hold_requests == []


def test_plan_explains_each_step_in_plain_words(client):
    hub = client.hub
    item = hold_item(hub)
    plan = item.to_dict(hub.session.t)["plan"]
    assert [p["kind"] for p in plan] == ["hold", "notice"]
    assert plan[0]["title"] == "Manage activity" and "You choose" in plan[0]["detail"]
    assert plan[0]["on"] == "approve"
    assert plan[1]["title"] == f"Notice to {item.draft['to']}" and plan[1]["on"] == "separate"
    assert "separately" in plan[1]["detail"]


# --- dismiss, watch, expire ------------------------------------------------------------------------------------


def test_dismiss_then_undo_within_the_window(client):
    hub = client.hub
    item = hold_item(hub)
    out = ok(client, item, "dismiss")
    assert out["status"] == "dismissed" and out["undo_left_s"] == hub.store.rules.handoff.undo_s
    hub.wall.now += 6
    assert ok(client, item, "undo")["status"] == "pending"
    assert item.resolved_clock is None


def test_undo_is_refused_after_the_window(client):
    hub = client.hub
    item = hold_item(hub)
    ok(client, item, "dismiss")
    hub.wall.now += hub.store.rules.handoff.undo_s + 0.5
    r = act(client, item, "undo")
    assert r.status_code == 409 and "window" in r.json()["detail"]
    assert item.status == "dismissed"


def test_dismissed_item_re_alerts_if_it_gets_worse(client):
    hub = client.hub
    item = hold_item(hub)
    ok(client, item, "dismiss")
    advance(hub, 2)
    assert hub._latest_item(item.contact_id) is item, "not worse: stays dismissed"
    item.severity = (0, 0)
    advance(hub, 1)
    fresh = hub._latest_item(item.contact_id)
    assert fresh is not item and fresh.status == "pending"


def test_keep_watching_rechecks_after_two_minutes(client):
    hub = client.hub
    item = hold_item(hub)
    out = ok(client, item, "watch")
    assert out["status"] == "watching" and out["watch_left_s"] == 120
    assert hub.budget()["watching"] == 1
    advance(hub, 121)
    assert item.status in ("pending", "stood_down")
    assert item.history[-1]["action"] in ("recheck", "stand_down")


def test_escalate_now_ends_keep_watching(client):
    item = hold_item(client.hub)
    ok(client, item, "watch")
    assert ok(client, item, "escalate")["status"] == "pending"
    assert item.snooze_until is None


def test_unanswered_item_expires_and_pages_the_backup_on_screen_only(client):
    hub = client.hub
    item = notice_only_item(hub)
    advance(hub, item.deadline_t - hub.session.t + 2)
    assert item.status == "expired" and item.paged and item.overdue
    assert hub.outbox == [] and hub.hold_requests == []
    assert hub.budget()["need_you"] >= 1 and hub.budget()["expired"] >= 1
    assert any(e["reason"] == "Backup officer paged on screen" for e in hub.audit)
    assert ok(client, item, "review")["status"] == "notice_review", "a late operator can still act"


@pytest.mark.parametrize("action", ["dismiss", "watch"])
def test_dismiss_and_watch_never_send_anything(client, action):
    hub = client.hub
    for item in [i for i in hub.items.values() if i.status == "pending"]:
        ok(client, item, action)
    advance(hub, 200, dt=2.0)
    assert hub.outbox == [] and hub.hold_requests == []


# --- illegal moves ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("state", hs.STATES)
def test_every_illegal_move_is_refused_and_changes_nothing(client, state):
    hub = client.hub
    item = hold_item(hub)
    item.status = state
    for action in hs.ACTIONS:
        if state in hs.OPERATOR_MOVES[action][0]:
            continue
        receipts, outbox, holds = len(hub.receipts), len(hub.outbox), len(hub.hold_requests)
        r = act(client, item, action, confirm=True, body="x")
        assert r.status_code == 409, (state, action)
        assert item.status == state
        assert (len(hub.receipts), len(hub.outbox), len(hub.hold_requests)) == (receipts, outbox, holds)


def test_unknown_and_missing_items(client):
    item = hold_item(client.hub)
    assert act(client, item, "execute").status_code == 422
    assert act(client, item, "reject").status_code == 422
    assert client.post("/api/handoff/H-999", json={"action": "approve"}).status_code == 404


def test_r4_r5_never_run_without_an_operator(client):
    hub = client.hub
    advance(hub, 400, dt=2.0)
    for _ in range(5):
        settle(client, 2)
    assert hub.outbox == [] and hub.hold_requests == []
    assert all(i.status in ("pending", "expired", "stood_down") for i in hub.items.values())
    assert all(e["actor"] == "system" for e in hub.audit if e["kind"] == "handoff")


# --- bookkeeping -----------------------------------------------------------------------------------------------


def test_every_transition_writes_a_receipt_and_audit_entry(client):
    hub = client.hub
    item = hold_item(hub)
    moves = [("approve", {}), (None, {}), ("review", {}), ("edit", {"body": "edited"}), ("send", {"confirm": True}),
             ("extend", {}), ("lift", {})]
    for action, body in moves:
        n = len(hub.receipts)
        if action is None:
            settle(client)
        else:
            ok(client, item, action, **body)
        new = [r for r in list(hub.receipts)[n:] if r.get("kind") == "handoff"]
        assert len(new) == 1, action
        seq = new[0]["seq"]
        assert any(e["seq"] == seq for e in hub.audit)
    assert [h["to"] for h in item.history] == ["pending", "hold_requesting", "hold_active", "notice_review",
                                                "notice_review", "notice_sent", "notice_sent", "lifted"]
    assert hub.budget()["holds"] == 0 and hub.budget()["resolved"] >= 1


def test_transitions_do_not_change_engine_decisions(client):
    hub = client.hub
    hub.running = False
    item = hold_item(hub)
    before = dict(hub.session.current[item.contact_id].to_dict())
    ok(client, item, "approve")
    settle(client)
    after = hub.session.current[item.contact_id].to_dict()
    assert before == after
    assert not any(r.get("kind") == "handoff" for r in hub.receipts if r["automated"])


def test_states_endpoint_matches_the_table(client):
    body = client.get("/api/handoff/states").json()
    assert set(body["states"]) == set(hs.STATES)
    assert body["operator"]["approve"] == {"from": ["pending", "expired"], "to": "hold_requesting"}
    assert body["operator"]["send"]["from"] == ["notice_review"]


# --- hold scope: this operation only, or the whole area -----------------------------------------------------------


def test_options_describe_the_operation_and_the_area(client):
    hub = client.hub
    item = hold_item(hub)
    opts = item.to_dict(hub.session.t)["hold_options"]
    op, area = opts["options"]
    assert (op["scope"], area["scope"]) == ("operation", "area")
    focus = item.decision["focus_asset"]
    assert focus["name"] in op["summary"] and len(op["summary"]) < 90
    assert [t["asset"] for t in op["targets"]] == [focus["name"]]
    assert focus["name"] in [t["asset"] for t in area["targets"]]
    assert opts["recommended"] in ("operation", "area") and opts["reason"]
    assert opts["radius_m"] == hub.store.rules.handoff.area_radius_m


def test_area_covers_every_active_operation_in_range_and_nothing_inactive(client):
    hub = client.hub
    rules = hub.store.rules
    item = hold_item(hub)
    area = item.hold_options["options"][1]
    inactive = {a.name for a in rules.assets if not a.active}
    assert not inactive & {t["asset"] for t in area["targets"]}
    assert len(area["targets"]) >= 1


def test_recommend_area_when_several_operations_are_in_range_else_operation(client):
    hub = client.hub
    rules = hub.store.rules
    d = dict(hold_item(hub).decision)
    rules.handoff.area_radius_m = 5000
    wide = hs.hold_options(d, rules)
    assert len(wide["options"][1]["targets"]) >= 2 and wide["recommended"] == "area"
    rules.handoff.area_radius_m = 1
    d2 = {**d, "urgency": "elevated", "trend": "steady"}
    tight = hs.hold_options(d2, rules)
    assert tight["recommended"] == "operation"
    assert hs.hold_options({**d2, "urgency": "urgent"}, rules)["recommended"] == "area"
    assert hs.hold_options({**d2, "trend": "closing", "consequence": "high"}, rules)["recommended"] == "area"
    assert hs.hold_options({**d, "rungs": ["R5"]}, rules) is None


def test_approve_needs_an_explicit_scope(client):
    hub = client.hub
    item = hold_item(hub)
    r = client.post(f"/api/handoff/{item.id}", json={"action": "approve"})
    assert r.status_code == 409 and "choose what to hold" in r.json()["detail"]
    assert client.post(f"/api/handoff/{item.id}", json={"action": "approve", "scope": "region"}).status_code == 422
    assert item.status == "pending" and hub.hold_requests == []


@pytest.mark.parametrize("scope", ["operation", "area"])
def test_hold_request_records_scope_and_targets(client, scope):
    hub = client.hub
    item = hold_item(hub)
    opts = item.hold_options
    chosen = next(o for o in opts["options"] if o["scope"] == scope)
    out = ok(client, item, "approve", scope=scope)
    req = hub.hold_requests[0]
    assert out["hold"]["scope"] == scope and req["scope"] == scope and req["targets"] == chosen["targets"]
    assert req["recommended"] == opts["recommended"]
    settle(client)
    assert item.status == "hold_active" and item.hold["targets"] == chosen["targets"]
    entry = next(e for e in hub.audit if e["kind"] == "operator" and e["detail"].get("action") == "approve")
    assert entry["detail"]["scope"] == scope and entry["detail"]["recommended"] == opts["recommended"]
    assert hub.outbox == []


def test_operator_can_override_the_recommendation_and_it_is_logged(client):
    hub = client.hub
    item = hold_item(hub)
    other = "operation" if item.hold_options["recommended"] == "area" else "area"
    ok(client, item, "approve", scope=other)
    entry = next(e for e in hub.audit if e["kind"] == "operator" and e["detail"].get("action") == "approve")
    assert "different scope than recommended" in entry["reason"]


def test_retry_keeps_the_scope_the_operator_chose(client):
    hub = client.hub
    hub.mock_hold_fail = True
    item = hold_item(hub)
    ok(client, item, "approve", scope="area")
    settle(client)
    hub.mock_hold_fail = False
    r = client.post(f"/api/handoff/{item.id}", json={"action": "retry", "operator": "Officer K"})
    assert r.status_code == 200 and r.json()["hold"]["scope"] == "area"

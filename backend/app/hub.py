from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import threading
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from . import handoff as hs
from .advisor import AdvisorCache
from .engine import Decision
from .geometry import format_latlon
from .rules import RulesStore, apply_ops, field_diff, load_yaml_text, parse_rules, plain
from .session import Session, World
from .twists import TwistHistory, preview

log = logging.getLogger("quietwater")

OPEN = hs.OPEN
ACTIVE = hs.OPEN + hs.IN_PROGRESS
DEFAULT_SCENARIO = {"security": "harbor_morning", "recovery": "lost_vehicle"}
SPEEDS = (1, 2, 5)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class HandoffItem:
    id: str
    contact_id: str
    created_t: float
    created_clock: str
    deadline_t: float
    decision: dict[str, Any]
    severity: tuple[int, int]
    status: str = "pending"
    overdue: bool = False
    contact_lost: bool = False
    snooze_until: float | None = None
    resolved_t: float | None = None
    resolved_clock: str | None = None
    actor: str | None = None
    note: str | None = None
    draft: dict[str, str] | None = None
    draft_status: str | None = None
    draft_edited: bool = False
    steps: list[dict[str, Any]] = field(default_factory=list)
    hold: dict[str, Any] | None = None
    review_from: str | None = None
    dismissed_wall: float | None = None
    paged: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, now: float, wall: float | None = None, undo_s: float = 0) -> dict[str, Any]:
        d = asdict(self)
        d["remaining_s"] = round(self.deadline_t - now, 1)
        d["window_s"] = self.decision.get("window_s")
        d["plan"] = hs.plan(self.decision, self.draft)
        watching = self.status == "watching" and self.snooze_until is not None
        d["watch_left_s"] = round(self.snooze_until - now, 1) if watching else None
        d["hold_left_s"] = round(self.hold["until_t"] - now, 1) if self.hold and self.hold.get("until_t") else None
        undo = None
        if self.status == "dismissed" and self.dismissed_wall is not None and wall is not None:
            undo = round(max(0.0, undo_s - (wall - self.dismissed_wall)), 1)
        d["undo_left_s"] = undo
        d.pop("dismissed_wall")
        return d


class Hub:
    def __init__(self, root: Path, autostart_scenario: str = "harbor_morning"):
        self.root = root
        self.config_dir = root / "config"
        self.data_dir = root / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.store = RulesStore(self.config_dir / "rules.yaml")
        self.world = World.load(self.config_dir)
        self.history = TwistHistory(self.data_dir / "twist_history.json")
        self.advisor_cache = AdvisorCache(self.data_dir / "advisor_cache.json")
        self.lock = threading.RLock()
        self.mode = "security"
        self.speed = 1.0
        self.running = True
        self.tick_s = 0.5
        self.seq = 0
        self.run_id = 0
        self.receipts: deque[dict[str, Any]] = deque(maxlen=5000)
        self.audit: deque[dict[str, Any]] = deque(maxlen=50000)
        self.items: dict[str, HandoffItem] = {}
        self.load_trace: deque[float] = deque(maxlen=240)
        self.outbox: list[dict[str, Any]] = []
        self.hold_requests: list[dict[str, Any]] = []
        self.wall = time.monotonic
        self.mock_hold_fail = os.environ.get("QUIETWATER_MOCK_HOLD_FAIL") == "1"
        self.subscribers: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._new_receipts: list[dict[str, Any]] = []
        self.session: Session
        self.load_scenario(autostart_scenario, actor="system")

    def _next(self) -> int:
        self.seq += 1
        return self.seq

    def log_audit(self, kind: str, actor: str, reason: str, contact_id: str | None = None,
                  rung: str | None = None, detail: Any = None) -> dict[str, Any]:
        entry = {"seq": self._next(), "wall": now_iso(), "t": round(self.session.t, 1),
                 "clock": self.session.clock, "kind": kind, "actor": actor,
                 "contact_id": contact_id, "rung": rung, "reason": reason, "detail": detail,
                 "mode": self.mode}
        self.audit.append(entry)
        return entry

    def load_scenario(self, name: str, seed: int | None = None, actor: str = "operator",
                      mode: str | None = None) -> None:
        with self.lock:
            try:
                self.world = World.load(self.config_dir)
            except Exception:
                log.exception("scenario/preset files are invalid; keeping the last good copy")
            scen = self.world.scenario(name)
            self.mode = mode or scen.get("mode", self.mode)
            self.session = Session(self.store.rules, self.world, name, self.mode, seed,
                                   advisor_cache=self.advisor_cache)
            self.run_id += 1
            self._new_receipts = []
            self.receipts.clear()
            self.items.clear()
            self.load_trace.clear()
            self.outbox.clear()
            self.hold_requests.clear()
            self.log_audit("scenario", actor, f"Loaded scenario '{scen.get('title', name)}' (seed {self.session.seed})",
                           detail={"scenario": name, "seed": self.session.seed, "mode": self.mode})

    def set_mode(self, mode: str, load: bool = True, actor: str = "operator") -> None:
        with self.lock:
            if load:
                self.load_scenario(DEFAULT_SCENARIO[mode], actor=actor, mode=mode)
            else:
                self.mode = mode
                self.session.mode = mode
            title = self.store.rules.modes[mode].title
            self.log_audit("mode", actor, f"Mode set to {title}", detail={"mode": mode})

    def control(self, action: str, speed: float | None = None, actor: str = "operator") -> None:
        with self.lock:
            if action == "play":
                self.running = True
            elif action == "pause":
                self.running = False
            elif action == "restart":
                self.load_scenario(self.session.scenario_name, self.session.seed, actor=actor, mode=self.mode)
                self.running = True
            elif action == "speed" and speed is not None:
                self.speed = min(SPEEDS, key=lambda s: abs(s - speed))
            else:
                raise ValueError(f"unknown control action '{action}'")
            self.log_audit("sim", actor, f"Simulator {action}" + (f" {self.speed}x" if action == "speed" else ""))

    def tick(self) -> None:
        with self.lock:
            changed = self.store.check_reload()
            if changed:
                self._on_rules_changed(*changed, source="file", note="Edited rules.yaml on disk", title="File edit")
            if self.running:
                self._advance(self.tick_s * self.speed)
            self._settle_holds()
            snap = self.snapshot()
        self._broadcast("tick", snap)

    def _advance(self, dt: float) -> None:
        changed = self.session.step(dt)
        for d in changed:
            self._record(d)
        self._update_items()
        self.load_trace.append(self.budget()["load"])

    def _record(self, d: Decision) -> None:
        receipt = {"id": f"D-{self.seq + 1:05d}", "contact_id": d.contact_id, "t": d.t, "clock": d.clock,
                   "automated": not d.requires_human, "rules_version": self.store.version,
                   "config_hash": self.session.advisor.config_hash, "mode": self.mode, "decision": d.to_dict()}
        advisor = None
        if d.advisor:
            advisor = {k: d.advisor[k] for k in ("source", "applied", "raised_rungs", "clamped", "error", "reason")}
        entry = self.log_audit("decision", "system", d.reason, d.contact_id, d.rung,
                               {"rungs": d.rungs, "path": d.path, "outcome": d.outcome,
                                "ruled_out": d.ruled_out, "automated": not d.requires_human,
                                "config_hash": receipt["config_hash"], "advisor": advisor})
        receipt["seq"] = entry["seq"]
        self.receipts.append(receipt)
        self._new_receipts.append(receipt)

    def _latest_item(self, contact_id: str) -> HandoffItem | None:
        found = [i for i in self.items.values() if i.contact_id == contact_id]
        return found[-1] if found else None

    def _steps(self, contact_id: str) -> list[dict[str, Any]]:
        out, last = [], None
        for r in self.receipts:
            if r["contact_id"] != contact_id or r.get("kind") == "handoff":
                continue
            d = r["decision"]
            names = " + ".join(f"{x} {n}" for x, n in zip(d["rungs"], d["rung_names"], strict=False))
            if names != last:
                out.append({"clock": r["clock"], "rungs": names, "reason": d["reason"], "automated": r["automated"]})
                last = names
        return out

    def _draft(self, d: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, str]:
        rules = self.store.rules
        recovery = d["track"] == "recovery"
        target = rules.handoff_target("recovery" if recovery else "security")
        n = rules.notice
        pos = format_latlon(tuple(d["position"]), rules.harbor.origin)
        asset = d.get("focus_asset")
        near = f", {asset['distance_m']} m from {asset['name']}" if asset else ""
        done = [s for s in steps if s["automated"]]
        lines = [
            f"{n.to}: {target}",
            f"{n.sender}: Harbor watch officer, {rules.harbor.name}",
        ]
        if recovery:
            drift = d.get("drift") or {}
            eta = drift.get("eta_critical")
            lines.append(f"SUBJECT: {rules.recovery.lost_vehicle_id} {n.subject_found} - {n.contact} {d['contact_id']}")
            lines += ["", f"At {d['clock']} sonar holds contact {d['contact_id']}, {d['label_text']} "
                          f"({round(d['confidence'] * 100)}%), at {pos}{near}.",
                      f"Drift: {drift.get('speed_kn')} kn toward {drift.get('heading')}°"
                      + (f"; reaches {eta['zone']} in about {eta['seconds'] // 60} min." if eta else "."),
                      f"Modem: {d['hail'].replace('_', ' ')}."]
        else:
            lines.append(f"SUBJECT: {n.subject_unknown}{near} - {n.contact} {d['contact_id']}")
            lines += ["", f"At {d['clock']} sonar contact {d['contact_id']}: {d['label_text']} "
                          f"({round(d['confidence'] * 100)}%), {d['size_m']:.1f} m, {d['speed_kn']} kn, "
                          f"heading {d['heading']}°, at {pos}{near}."]
        lines += [
            f"{n.why}: {d['reason']}",
            f"{n.ruled_out}: {', '.join(d['ruled_out']).lower() or n.nothing_yet}.",
            f"{n.steps}: " + ("; ".join(f"{s['clock']} {s['rungs']}" for s in done) or n.none) + ".",
            f"{n.recommended}: {d['recommendation']}",
            "",
            n.closing,
        ]
        subject = lines[2].removeprefix("SUBJECT: ")
        return {"to": target, "subject": subject, "language": rules.language, "body": "\n".join(lines)}

    def _redraft(self, item: HandoffItem) -> None:
        """Keep the drafted notice current until the operator opens, edits or sends it."""
        if "R5" not in item.decision["rungs"] or item.draft_status == "sent" or item.draft_edited:
            return
        if item.status == "notice_review":
            return
        item.draft = self._draft(item.decision, item.steps)
        item.draft_status = "drafted"

    def _move(self, item: HandoffItem, action: str, actor: str, system: bool = False, note: str | None = None,
              to: str | None = None, detail: dict[str, Any] | None = None) -> None:
        """The only place an item changes state. Writes the audit entry and a decision receipt."""
        before = item.status
        dest = hs.target(action, before, system=system)
        item.status = to or dest or before
        s = self.session
        if item.status in hs.FINAL:
            item.resolved_t, item.resolved_clock = s.t, s.clock
        if not system:
            item.actor = actor
            if note:
                item.note = note
        msg = hs.LABELS[action] + (f" - {note}" if note else "")
        item.history.append({"action": action, "from": before, "to": item.status, "actor": actor,
                             "clock": s.clock, "t": round(s.t, 1)})
        info = {"item": item.id, "action": action, "from": before, "to": item.status, **(detail or {})}
        entry = self.log_audit("handoff" if system else "operator", actor, msg, item.contact_id,
                               item.decision.get("rung"), info)
        receipt = {"id": f"D-{entry['seq']:05d}", "seq": entry["seq"], "kind": "handoff",
                   "contact_id": item.contact_id, "t": round(s.t, 1), "clock": s.clock, "automated": False,
                   "rules_version": self.store.version, "config_hash": self.session.advisor.config_hash,
                   "mode": self.mode, "decision": item.decision,
                   "transition": {"item": item.id, "action": action, "from": before, "to": item.status,
                                  "actor": actor, "label": msg}}
        self.receipts.append(receipt)
        self._new_receipts.append(receipt)

    def _update_items(self) -> None:
        s = self.session
        t = s.t
        for cid, d in s.current.items():
            item = self._latest_item(cid)
            if d.requires_human:
                if item is None or (item.status in hs.FINAL and d.severity() > tuple(item.severity)):
                    self._create_item(d)
                    continue
                if item.status not in ACTIVE:
                    continue
                if item.status in OPEN and d.severity() > tuple(item.severity):
                    item.severity = d.severity()
                    item.deadline_t = min(item.deadline_t, t + (d.window_s or 0))
                    item.overdue = False
                    item.decision = d.to_dict()
                    self._move(item, "escalate", "system", system=True, note=d.reason)
                if item.status == "watching" and item.snooze_until is not None and t >= item.snooze_until:
                    self._move(item, "recheck", "system", system=True)
                item.decision = d.to_dict()
                item.steps = self._steps(cid)
                self._redraft(item)
            elif item and item.status in OPEN:
                item.decision = d.to_dict()
                item.note = d.reason
                item.actor = "system"
                self._move(item, "stand_down", "system", system=True, note=d.reason)
        for item in self.items.values():
            if item.status in ACTIVE and item.contact_id in s.departed and not item.contact_lost:
                item.contact_lost = True
                self.log_audit("handoff", "system", "Contact lost from sonar; item kept open", item.contact_id)
            if item.status == "pending" and t > item.deadline_t:
                item.overdue = True
                item.paged = True
                self._move(item, "expire", "system", system=True)
            hold = item.hold
            if hold and hold.get("status") == "active" and not hold.get("time_up") and t >= hold["until_t"]:
                hold["time_up"] = True
                self.log_audit("handoff", "system", "Hold timer ended; the hold stays until you lift it",
                               item.contact_id, item.decision.get("rung"), {"item": item.id})

    def _create_item(self, d: Decision) -> None:
        s = self.session
        item = HandoffItem(
            id=f"H-{len(self.items) + 1:03d}", contact_id=d.contact_id, created_t=s.t, created_clock=s.clock,
            deadline_t=s.t + (d.window_s or self.store.rules.windows.default), decision=d.to_dict(),
            severity=d.severity(), steps=self._steps(d.contact_id))
        self._redraft(item)
        item.history.append({"action": "create", "from": None, "to": "pending", "actor": "system",
                             "clock": s.clock, "t": round(s.t, 1)})
        self.items[item.id] = item
        self.log_audit("handoff", "system", f"Needs you: {d.recommendation}", d.contact_id, d.rung,
                       {"item": item.id, "urgency": d.urgency, "window_s": d.window_s})

    def _settle_holds(self) -> None:
        """Answer mock hold requests after `mock_hold_delay_s` of wall time."""
        delay = self.store.rules.handoff.mock_hold_delay_s
        now = self.wall()
        for item in self.items.values():
            hold = item.hold
            if item.status != "hold_requesting" or not hold or now - hold["requested_wall"] < delay:
                continue
            req = next(r for r in self.hold_requests if r["id"] == hold["request_id"])
            if self.mock_hold_fail:
                hold["status"] = "failed"
                req["result"] = "failed"
                self._move(item, "hold_failed", "system", system=True,
                           detail={"request": req["id"], "error": "terminal operations did not confirm (mock)"})
            else:
                hold["status"] = "active"
                hold["until_t"] = round(self.session.t + self.store.rules.handoff.hold_s, 1)
                hold["confirmed_clock"] = self.session.clock
                req["result"] = "confirmed"
                self._move(item, "hold_confirmed", "system", system=True, detail={"request": req["id"]})

    def _request_hold(self, item: HandoffItem, operator: str) -> dict[str, Any]:
        step = hs.hold_step(item.decision)
        if step is None:
            raise hs.IllegalMove("this item has no hold to approve; review the notice instead")
        req = {"id": f"HR-{len(self.hold_requests) + 1:03d}", "item": item.id, "contact_id": item.contact_id,
               "asset": step["asset"], "operation": step["operation"], "requested_by": operator,
               "clock": self.session.clock, "at": now_iso(), "mock": True, "result": "pending"}
        self.hold_requests.append(req)
        item.hold = {"status": "requesting", "request_id": req["id"], "asset": step["asset"],
                     "operation": step["operation"], "title": step["title"], "requested_clock": self.session.clock,
                     "requested_wall": self.wall(), "until_t": None}
        return req

    def act(self, item_id: str, action: str, operator: str, note: str | None = None,
            body: str | None = None, confirm: bool = False) -> HandoffItem:
        with self.lock:
            item = self.items.get(item_id)
            if item is None:
                raise KeyError(f"no handoff item {item_id}")
            cfg = self.store.rules.handoff
            hs.target(action, item.status)
            detail: dict[str, Any] = {}
            to = None
            if action in ("approve", "retry"):
                if action == "retry":
                    item.hold = None
                detail["request"] = self._request_hold(item, operator)["id"]
            elif action == "review":
                if not item.draft or item.draft_status == "sent":
                    raise hs.IllegalMove("there is no unsent notice to review")
                item.review_from = item.status
            elif action == "edit":
                if not body or not body.strip():
                    raise hs.IllegalMove("the notice can't be empty")
                item.draft = {**item.draft, "body": body}
                item.draft_edited = True
            elif action == "cancel":
                to = item.review_from or "pending"
                item.review_from = None
            elif action == "send":
                if not confirm:
                    raise hs.IllegalMove(f"confirm before sending to {item.draft['to']}")
                item.draft_status = "sent"
                item.review_from = None
                self.outbox.append({"at": now_iso(), "clock": self.session.clock, "item": item.id, "by": operator,
                                    **item.draft})
                detail["to"] = item.draft["to"]
                note = note or f"to {item.draft['to']} (mock outbox, not transmitted)"
            elif action == "dismiss":
                item.dismissed_wall = self.wall()
            elif action == "undo":
                if item.dismissed_wall is None or self.wall() - item.dismissed_wall > cfg.undo_s:
                    raise hs.IllegalMove("the undo window has closed")
                item.dismissed_wall = None
                item.resolved_t = item.resolved_clock = None
            elif action == "watch":
                item.snooze_until = self.session.t + self.store.rules.alert_budget.keep_watching_snooze_s
            elif action == "escalate":
                item.snooze_until = None
            elif action in ("lift", "resolve", "extend"):
                hold = item.hold
                active = bool(hold and hold["status"] == "active")
                if action == "resolve" and active:
                    raise hs.IllegalMove("lift the hold before marking this resolved")
                if action != "resolve" and not active:
                    raise hs.IllegalMove("there is no active hold")
                if action == "lift":
                    hold["status"] = "lifted"
                    hold["lifted_clock"] = self.session.clock
                elif action == "extend":
                    hold["until_t"] = round(max(hold["until_t"], self.session.t) + cfg.hold_s, 1)
                    hold["time_up"] = False
            self._move(item, action, operator, note=note, to=to, detail=detail)
            snap = self.snapshot()
        self._broadcast("tick", snap)
        return item

    def budget(self) -> dict[str, Any]:
        s = self.session
        cfg = self.store.rules.alert_budget
        items = list(self.items.values())
        pending = [i for i in items if i.status in hs.WAITING]
        load = sum(cfg.weights.get(i.decision.get("rung"), 0) for i in pending)
        human = set(s.first_human_t)
        counts = Counter(d.rung for d in s.current.values())
        auto = sum(1 for r in self.receipts if r["automated"] and r["decision"]["rung"] != "R0")
        states = Counter(i.status for i in items)
        return {
            "seen": len(s.seen), "total": len(s.seen), "needed_operator": len(human),
            "active": len(s.current), "quiet": len(s.seen) - len(human),
            "need_you": len(pending), "watching": states["watching"],
            "holds": sum(1 for i in items if i.hold and i.hold["status"] == "active"),
            "in_progress": sum(states[k] for k in hs.IN_PROGRESS),
            "notices_sent": sum(1 for i in items if i.draft_status == "sent"),
            "dismissed": states["dismissed"], "expired": states["expired"],
            "resolved": sum(states[k] for k in hs.FINAL),
            "states": dict(states),
            "load": load, "capacity": cfg.capacity, "over": load > cfg.capacity,
            "bang": len(s.seen), "rung_counts": {r: counts.get(r, 0) for r in ("R0", "R1", "R2", "R3", "R4", "R5")},
            "automated_actions": auto, "trace": list(self.load_trace)[-120:],
        }

    def contacts_payload(self) -> list[dict[str, Any]]:
        out = []
        for cid, c in self.session.sim.active.items():
            d = self.session.current.get(cid)
            if d is None:
                continue
            trail = list(c.trail)[::-3][:14][::-1]
            out.append({
                "id": cid, "x": round(c.x, 1), "y": round(c.y, 1), "heading": round(c.heading),
                "speed_kn": d.speed_kn, "size_m": c.size_m, "label": d.label, "label_text": d.label_text,
                "confidence": d.confidence, "rung": d.rung, "rungs": d.rungs, "rung_names": d.rung_names,
                "urgency": d.urgency, "requires_human": d.requires_human, "outcome": d.outcome,
                "zone": d.zone, "registry_id": d.registry_id, "track": d.track, "reason": d.reason,
                "trail": [[round(p[1]), round(p[2])] for p in trail],
            })
        return out

    def snapshot(self) -> dict[str, Any]:
        s = self.session
        new, self._new_receipts = self._new_receipts, []
        order = {"urgent": 0, "elevated": 1, "routine": 2}
        stage = {"pending": 0, "expired": 0, "notice_review": 1, "hold_failed": 1, "hold_requesting": 2,
                 "hold_active": 2, "notice_sent": 2, "watching": 3}
        items = sorted(self.items.values(), key=lambda i: (
            stage.get(i.status, 9), order.get(i.decision.get("urgency"), 3),
            i.deadline_t if i.status in ACTIVE else -(i.resolved_t or 0)))
        wall, undo_s = self.wall(), self.store.rules.handoff.undo_s
        return {
            "run": self.run_id, "t": round(s.t, 1), "clock": s.clock, "running": self.running, "speed": self.speed,
            "scenario": {"id": s.scenario_name, "title": s.scenario.get("title", s.scenario_name),
                         "description": s.scenario.get("description", ""), "duration_s": s.duration_s, "seed": s.seed},
            "mode": self.mode,
            "rules": {"version": self.store.version, "error": self.store.error},
            "contacts": self.contacts_payload(),
            "items": [i.to_dict(s.t, wall, undo_s) for i in items[:40]],
            "budget": self.budget(),
            "receipts": new,
        }

    def hello(self) -> dict[str, Any]:
        with self.lock:
            snap = self.snapshot()
            snap["receipts"] = list(self.receipts)[-400:]
            snap["history"] = self.history.public()
            return snap

    def _broadcast(self, event: str, payload: dict[str, Any]) -> None:
        if self.loop is None:
            return
        msg = f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
        try:
            same = asyncio.get_running_loop() is self.loop
        except RuntimeError:
            same = False
        if same:
            self._fanout(msg)
        else:
            self.loop.call_soon_threadsafe(self._fanout, msg)

    def _fanout(self, msg: str) -> None:
        for q in list(self.subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(msg)

    def config_payload(self) -> dict[str, Any]:
        return {"harbor": self.world.harbor, "rules": self.store.data, "version": self.store.version,
                "error": self.store.error, "scenarios": self.world.scenario_list(), "presets": self.world.presets}

    def candidate(self, body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        if body.get("yaml") is not None:
            data = plain(load_yaml_text(body["yaml"]))
            parse_rules(data)
            return data, body["yaml"]
        if body.get("rules") is not None:
            parse_rules(body["rules"])
            return body["rules"], None
        if body.get("ops"):
            data = apply_ops(self.store.data, body["ops"])
            parse_rules(data)
            return data, None
        raise ValueError("send one of: yaml, rules, ops")

    def preview(self, data: dict[str, Any], scenario: str | None = None, seed: int | None = None) -> dict[str, Any]:
        with self.lock:
            before = self.store.rules
            before_data = self.store.data
            scen = scenario or self.session.scenario_name
            seed = seed if seed is not None else (self.session.seed if scen == self.session.scenario_name else None)
            mode = self.mode
        impact = preview(before, parse_rules(data), self.world, scen, mode, seed, self.advisor_cache)
        return {"changes": field_diff(before_data, data), "impact": impact}

    def apply(self, data: dict[str, Any], text: str | None, note: str, title: str, source: str,
              impact: dict[str, Any] | None) -> dict[str, Any]:
        with self.lock:
            before_text = self.store.text
            before, after = self.store.write_text(text) if text is not None else self.store.write_data(data)
            return self._on_rules_changed(before, after, source=source, note=note, title=title, impact=impact,
                                          before_text=before_text)

    def revert(self, entry_id: str, operator: str) -> dict[str, Any]:
        entry = self.history.get(entry_id)
        if entry is None or not entry.get("before_text"):
            raise KeyError(f"no twist {entry_id} to revert")
        data, _ = self.store.validate_text(entry["before_text"])
        impact = self.preview(data)["impact"]
        return self.apply(data, entry["before_text"], note=f"Reverted {entry_id} ({entry.get('title', '')})",
                          title=f"Revert {entry_id}", source="revert", impact=impact)

    def _on_rules_changed(self, before: dict[str, Any], after: dict[str, Any], source: str, note: str, title: str,
                          impact: dict[str, Any] | None = None, before_text: str | None = None) -> dict[str, Any]:
        self.session.set_rules(self.store.rules)
        changes = field_diff(before, after)
        if before_text is None:
            buf = io.StringIO()
            YAML().dump(before, buf)
            before_text = buf.getvalue()
        entry = self.history.add(source=source, title=title, note=note, rules_version=self.store.version,
                                 clock=self.session.clock, scenario=self.session.scenario_name, changes=changes,
                                 impact=_impact_summary(impact), before_text=before_text)
        self.log_audit("rules", "operator" if source != "file" else "file",
                       f"Rules v{self.store.version}: {title}" + (f" - {note}" if note else ""),
                       detail={"twist": entry["id"], "changes": changes})
        if impact is None:
            threading.Thread(target=self._impact_later, args=(entry["id"], before, after), daemon=True).start()
        self._broadcast("history", {"history": self.history.public()})
        return entry

    def _impact_later(self, entry_id: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        try:
            impact = preview(parse_rules(before), parse_rules(after), self.world, self.session.scenario_name,
                             self.mode, self.session.seed, self.advisor_cache)
            self.history.update(entry_id, impact=_impact_summary(impact))
            self._broadcast("history", {"history": self.history.public()})
        except Exception:
            log.exception("impact preview failed")

    def export(self, fmt: str) -> tuple[str, str]:
        with self.lock:
            rows = list(self.audit)
        if fmt == "json":
            return json.dumps({"exported_at": now_iso(), "entries": rows, "outbox": self.outbox,
                               "hold_requests": self.hold_requests}, indent=1), \
                "application/json"
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["seq", "wall_time", "sim_clock", "mode", "kind", "actor", "contact_id", "rung", "reason", "detail"])
        for r in rows:
            w.writerow([r["seq"], r["wall"], r["clock"], r["mode"], r["kind"], r["actor"], r["contact_id"] or "",
                        r["rung"] or "", r["reason"], json.dumps(r["detail"]) if r["detail"] is not None else ""])
        return buf.getvalue(), "text/csv"

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(self.tick_s)
            try:
                self.tick()
            except Exception:
                log.exception("tick failed")


def _impact_summary(impact: dict[str, Any] | None) -> dict[str, Any] | None:
    if impact is None:
        return None
    return {k: v for k, v in impact.items() if k != "rows"} | {
        "rows": [r for r in impact["rows"] if r["changed"]][:50]}

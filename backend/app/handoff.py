"""Hand-off item states and the only legal moves between them.

Engine decisions never change here. This module only tracks what the operator has
authorised for an R4/R5 item. Nothing leaves the building except through `approve`
(a mock hold request) and `send` (the drafted notice), and both need a person.
"""

from __future__ import annotations

from typing import Any

from .geometry import distance_to

# Waiting on a person: counted as "need you" in the Alert Budget.
WAITING = ("pending", "expired")
# The engine may still re-escalate, stand down or redraft these.
OPEN = ("pending", "watching", "expired")
# Work in progress after the operator acted.
IN_PROGRESS = ("hold_requesting", "hold_active", "hold_failed", "notice_review", "notice_sent")
FINAL = ("dismissed", "resolved", "lifted", "stood_down")
STATES = OPEN + IN_PROGRESS + FINAL

# action -> (states it is legal from, state it moves to). None means "back to where it came from"
# for cancel, and "stay put" for edit/extend.
OPERATOR_MOVES: dict[str, tuple[tuple[str, ...], str | None]] = {
    "approve": (WAITING, "hold_requesting"),
    "retry": (("hold_failed",), "hold_requesting"),
    "review": (WAITING + ("hold_active", "hold_failed"), "notice_review"),
    "edit": (("notice_review",), None),
    "cancel": (("notice_review",), None),
    "send": (("notice_review",), "notice_sent"),
    "dismiss": (OPEN, "dismissed"),
    "undo": (("dismissed",), "pending"),
    "watch": (WAITING, "watching"),
    "escalate": (("watching",), "pending"),
    "lift": (("hold_active", "notice_sent"), "lifted"),
    # An active hold is only ever ended by lifting it, so resolve needs no hold in place.
    "resolve": (("hold_failed", "notice_sent"), "resolved"),
    "extend": (("hold_active", "notice_sent"), None),
}
ACTIONS = tuple(OPERATOR_MOVES)

SYSTEM_MOVES: dict[str, tuple[tuple[str, ...], str]] = {
    "hold_confirmed": (("hold_requesting",), "hold_active"),
    "hold_failed": (("hold_requesting",), "hold_failed"),
    "expire": (("pending",), "expired"),
    "recheck": (("watching",), "pending"),
    "escalate": (OPEN, "pending"),
    "stand_down": (OPEN, "stood_down"),
}

LABELS = {
    "approve": "Placed hold", "retry": "Retried hold request", "review": "Opened notice for review",
    "edit": "Edited notice", "cancel": "Closed notice without sending", "send": "Sent notice",
    "dismiss": "Dismissed", "undo": "Undid dismiss", "watch": "Keep watching", "escalate": "Escalated now",
    "lift": "Lifted hold", "resolve": "Marked resolved", "extend": "Extended hold",
    "hold_confirmed": "Hold confirmed by terminal operations (mock)",
    "hold_failed": "Hold request failed (mock)", "expire": "Backup officer paged on screen",
    "recheck": "Keep-watching timer ended; back in your queue", "stand_down": "Stood down",
}


class IllegalMove(ValueError):
    pass


def target(action: str, status: str, system: bool = False) -> str | None:
    """Where `action` takes an item in `status`. Raises IllegalMove if it can't go there."""
    table = SYSTEM_MOVES if system else OPERATOR_MOVES
    if action not in table:
        raise IllegalMove(f"unknown action '{action}'")
    allowed, to = table[action]
    if status not in allowed:
        raise IllegalMove(f"can't {action} an item that is {status.replace('_', ' ')}")
    return to


SCOPES = ("operation", "area")


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def hold_options(decision: dict[str, Any], rules: Any, radius_m: float | None = None) -> dict[str, Any] | None:
    """What the operator can hold, and which choice we recommend. Always the operator's call.

    "operation" holds the one activity the contact threatens. "area" holds every active
    operation within `handoff.area_radius_m` of the contact.
    """
    if "R4" not in decision.get("rungs", []):
        return None
    focus = decision.get("focus_asset") or {}
    pos = tuple(decision["position"])
    radius = radius_m if radius_m is not None else rules.handoff.area_radius_m
    near = []
    for a in rules.assets:
        if a.active and distance_to(pos, a.shape) <= radius:
            near.append(a)
    if focus and not any(a.id == focus.get("id") for a in near):
        near += [a for a in rules.assets if a.id == focus.get("id")]
    near.sort(key=lambda a: distance_to(pos, a.shape))
    name = focus.get("name") or "the nearest berth"
    op = focus.get("operation") or "operations"
    recovery = decision.get("track") == "recovery"
    zone = decision.get("zone") or "this part of the harbor"
    operation = {
        "scope": "operation", "title": "This operation only",
        "action": f"Pause {op}",
        "summary": f"{_cap(op)} at {name}. Nothing else stops.",
        "targets": [{"asset": name, "operation": op}],
        "detail": f"Sends a hold request to {name} operations"
                  + (" until the vehicle is recovered." if recovery else "."),
    }
    targets = [{"asset": a.name, "operation": a.operation} for a in near]
    area = {
        "scope": "area", "title": "This entire area",
        "action": "Hold the area",
        "summary": f"Every active operation within {radius:.0f} m of the contact, around {zone}: "
                   + ", ".join(f"{t['operation']} at {t['asset']}" for t in targets) + ". "
                   "A wider pause that costs more, and removes more risk.",
        "targets": targets,
        "detail": f"Sends a hold request to {len(targets)} operation{'s' if len(targets) != 1 else ''}"
                  + (" until the vehicle is recovered." if recovery else "."),
    }
    if len(targets) >= 2:
        pick, why = "area", f"{len(targets)} operations are within {radius:.0f} m of the contact."
    elif decision.get("urgency") == "urgent":
        pick, why = "area", "The contact is flagged urgent."
    elif decision.get("trend") == "closing" and decision.get("consequence") == "high":
        pick, why = "area", "The contact is closing on a high-consequence asset."
    else:
        pick, why = "operation", "Only one operation is within range of the contact."
    return {"options": [operation, area], "recommended": pick, "reason": why, "radius_m": radius}


def plan(draft: dict[str, Any] | None, options: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Plain-language list of what the operator can do, in order."""
    steps = []
    if options:
        steps.append({"kind": "hold", "rung": "R4", "title": "Manage activity",
                      "detail": "Hold this operation only, or the whole area. You choose.", "on": "approve"})
    if draft:
        steps.append({"kind": "notice", "rung": "R5", "title": f"Notice to {draft['to']}",
                      "detail": "Already drafted. You review and send it separately.", "on": "separate"})
    return steps

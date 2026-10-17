"""Hand-off item states and the only legal moves between them.

Engine decisions never change here. This module only tracks what the operator has
authorised for an R4/R5 item. Nothing leaves the building except through `approve`
(a mock hold request) and `send` (the drafted notice), and both need a person.
"""

from __future__ import annotations

from typing import Any

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
    "approve": "Approved hold", "retry": "Retried hold request", "review": "Opened notice for review",
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


def hold_step(decision: dict[str, Any]) -> dict[str, Any] | None:
    """The one local action Approve authorises: R4 hold at the focus asset."""
    if "R4" not in decision.get("rungs", []):
        return None
    asset = decision.get("focus_asset") or {}
    name = asset.get("name") or "the nearest berth"
    operation = asset.get("operation") or "operations"
    recovery = decision.get("track") == "recovery"
    return {
        "kind": "hold", "rung": "R4", "asset": name, "operation": operation,
        "title": f"Pause {operation} at {name}",
        "detail": f"Sends a hold request to {name} operations"
                  + (" until the vehicle is recovered." if recovery else "."),
    }


def plan(decision: dict[str, Any], draft: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Plain-language list of what happens if the operator approves, in order."""
    steps = []
    hold = hold_step(decision)
    if hold:
        steps.append({**hold, "on": "approve"})
    if draft:
        steps.append({"kind": "notice", "rung": "R5", "title": f"Notice to {draft['to']}",
                      "detail": "Already drafted. You review and send it separately.", "on": "separate"})
    return steps

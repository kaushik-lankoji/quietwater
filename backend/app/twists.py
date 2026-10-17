from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .advisor import AdvisorCache
from .engine import Decision
from .rules import Rules
from .session import Session, World


def _compact(d: Decision | None) -> dict[str, Any] | None:
    if d is None:
        return None
    return {"rungs": d.rungs, "rung": d.rung, "rung_names": d.rung_names, "outcome": d.outcome,
            "reason": d.reason, "requires_human": d.requires_human, "urgency": d.urgency, "path": d.path,
            "label_text": d.label_text, "ai_raised_tier": d.ai_raised_tier, "ai_reason": d.ai_reason}


def _direction(pa: Decision | None, pb: Decision | None, sa: tuple, sb: tuple) -> str:
    if pa and pb and pa.requires_human != pb.requires_human:
        return "up" if pb.requires_human else "down"
    return "up" if sb > sa else "down" if sb < sa else "same"


def run_scenario(rules: Rules, world: World, scenario: str, mode: str, seed: int | None,
                 advisor_cache: AdvisorCache | None = None) -> Session:
    s = Session(rules, world, scenario, mode, seed, advisor_cache=advisor_cache)
    size = len(s.sim.pending)
    s.run(dt=1.0 if size <= 60 else 2.0)
    return s


def _totals(s: Session) -> dict[str, int]:
    human = sum(1 for cid in s.seen if s.peak.get(cid) and s.peak[cid].requires_human)
    return {"contacts": len(s.seen), "quiet": len(s.seen) - human, "need_you": human}


def preview(before: Rules, after: Rules, world: World, scenario: str, mode: str,
            seed: int | None, advisor_cache: AdvisorCache | None = None) -> dict[str, Any]:
    a = run_scenario(before, world, scenario, mode, seed, advisor_cache)
    b = run_scenario(after, world, scenario, mode, seed, advisor_cache)
    rows = []
    for cid in dict.fromkeys(a.seen + b.seen):
        pa, pb = a.peak.get(cid), b.peak.get(cid)
        sa = pa.severity() if pa else (-1, -1)
        sb = pb.severity() if pb else (-1, -1)
        changed = pa and pb and (pa.rungs != pb.rungs or pa.outcome != pb.outcome or pa.path != pb.path
                                 or pa.requires_human != pb.requires_human)
        ta, tb = a.first_human_t.get(cid), b.first_human_t.get(cid)
        timing = ta is not None and tb is not None and abs(ta - tb) >= 5
        rows.append({
            "contact_id": cid,
            "label": (pb or pa).label_text if (pb or pa) else "",
            "before": _compact(pa), "after": _compact(pb),
            "changed": bool(changed or timing or (pa is None) != (pb is None)),
            "direction": _direction(pa, pb, sa, sb),
            "first_human_t": {"before": ta, "after": tb},
        })
    rows.sort(key=lambda r: (not r["changed"], r["contact_id"]))
    return {
        "scenario": scenario, "mode": mode, "seed": a.seed, "duration_s": a.duration_s,
        "before": _totals(a), "after": _totals(b),
        "changed": sum(1 for r in rows if r["changed"]), "rows": rows,
    }


class TwistHistory:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.entries: list[dict[str, Any]] = []
        if path.exists():
            try:
                self.entries = json.loads(path.read_text())
            except json.JSONDecodeError:
                self.entries = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, indent=1))
        tmp.replace(self.path)

    def add(self, **fields: Any) -> dict[str, Any]:
        with self.lock:
            entry = {"id": f"T-{len(self.entries) + 1:03d}",
                     "at": datetime.now(UTC).isoformat(timespec="seconds"), **fields}
            self.entries.append(entry)
            self._save()
            return entry

    def update(self, entry_id: str, **fields: Any) -> None:
        with self.lock:
            for e in self.entries:
                if e["id"] == entry_id:
                    e.update(fields)
            self._save()

    def get(self, entry_id: str) -> dict[str, Any] | None:
        return next((e for e in self.entries if e["id"] == entry_id), None)

    def public(self) -> list[dict[str, Any]]:
        return [{k: v for k, v in e.items() if k not in ("before_text",)} for e in reversed(self.entries)]

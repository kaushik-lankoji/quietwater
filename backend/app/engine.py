from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .facts import MPS_TO_KN, Facts, project, resolve_zone
from .geometry import distance_to
from .rules import RUNGS, Rules, rung_index

DISPLAY = {
    "research_auv": "Research AUV",
    "commercial_rov": "Commercial ROV",
    "military_uuv": "Military-grade UUV",
    "improvised_device": "Improvised device",
    "biologic": "Marine life",
    "debris": "Debris",
    "unknown": "Unknown vehicle",
}
URGENCY_RANK = {"routine": 0, "elevated": 1, "urgent": 2}
LATCHING = ("threat", "evasive")
LIVE_FIELDS = ("t", "clock", "position", "heading", "speed_kn", "checks", "ruled_out", "consequence",
               "nearest_asset", "zone", "traffic", "confidence", "hail", "hail_route", "trend",
               "closing_mps", "cpa")


def display_label(label: str) -> str:
    return DISPLAY.get(label, label.replace("_", " ").capitalize())


def pct(x: float) -> str:
    return f"{round(x * 100)}%"


@dataclass
class Memory:
    second_looks: int = 0
    next_look_t: float | None = None
    escalated: bool = False
    hailed_t: float | None = None
    first_seen_t: float | None = None
    latched: Decision | None = None


@dataclass
class Decision:
    contact_id: str
    t: float
    clock: str
    track: str
    outcome: str
    rungs: list[str]
    rung: str
    rung_names: list[str]
    path: list[str]
    reason: str
    checks: list[dict[str, Any]]
    ruled_out: list[str]
    urgency: str
    window_s: float | None
    requires_human: bool
    recommendation: str
    why_higher: str
    why_lower: str
    notice: str | None
    label: str
    label_text: str
    confidence: float
    category: str
    consequence: str
    nearest_asset: dict[str, Any] | None
    focus_asset: dict[str, Any] | None
    position: tuple[float, float]
    heading: float
    speed_kn: float
    size_m: float
    zone: str
    registered: bool
    registry_id: str | None
    hail: str
    hail_route: str
    approval_role: str | None
    look: int
    max_looks: int
    traffic: list[str] = field(default_factory=list)
    drift: dict[str, Any] | None = None
    scan_label: str = "unknown"
    trend: str = "new"
    closing_mps: float = 0.0
    cpa: dict[str, Any] | None = None
    consequence_basis: str = "distance"
    ambiguous: bool = False
    ai_raised_tier: int = 0
    ai_reason: str | None = None
    advisor: dict[str, Any] | None = None

    def key(self) -> tuple:
        return (tuple(self.rungs), tuple(self.path), self.outcome, self.label, self.look, self.urgency)

    def severity(self) -> tuple[int, int]:
        return rung_index(self.rung), URGENCY_RANK[self.urgency]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["position"] = [round(self.position[0], 1), round(self.position[1], 1)]
        return d


class _Ctx:
    def __init__(self, f: Facts, mem: Memory, rules: Rules, track: str, mode: str):
        self.f, self.mem, self.rules, self.track = f, mem, rules, track
        self.path: list[str] = []
        self.text_mode = mode
        self.texts = rules.modes[mode]

    def name(self, rung: str) -> str:
        return f"{rung} {self.texts.rungs[rung].name}"

    def above(self, rungs: list[str]) -> str | None:
        i = max(rung_index(r) for r in rungs)
        return RUNGS[i + 1] if i + 1 < len(RUNGS) else None

    def below(self, rungs: list[str]) -> str | None:
        i = min(rung_index(r) for r in rungs)
        return RUNGS[i - 1] if i > 0 else None


def _shift(rungs: list[str], by: int) -> list[str]:
    return sorted({RUNGS[min(len(RUNGS) - 1, rung_index(r) + by)] for r in rungs}, key=rung_index)


def _who(f: Facts) -> str:
    return f.registry_id or display_label(f.label)


def _dist(f: Facts) -> str:
    a = f.nearest_asset
    return f"{a.distance_m:.0f} m from {a.name}" if a else "far from any asset"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _focus(f: Facts):
    return f.approaching or f.nearest_asset


def build_checks(f: Facts, rules: Rules) -> list[dict[str, Any]]:
    thr = rules.thresholds
    checks: list[dict[str, Any]] = []

    def add(key: str, label: str, ruled_out: bool | None, detail: str) -> None:
        checks.append({"key": key, "label": label, "ruled_out": ruled_out, "detail": detail})

    conf_txt = f"{display_label(f.label)} {pct(f.confidence)}"
    if f.category == "non_vehicle":
        add("non_vehicle", "Fish or debris", False if f.confidence >= thr.non_vehicle_confidence else None, conf_txt)
    elif f.confidence >= thr.classify_confidence:
        add("non_vehicle", "Fish or debris", True, f"vehicle: {conf_txt}")
    else:
        add("non_vehicle", "Fish or debris", None, f"not sure yet: {conf_txt}")

    ident = "Registered, scheduled, in its zone"
    if f.registered and f.scheduled and f.zone_authorized:
        add("identity", ident, False, f"{f.registry_id}, {f.schedule_note}")
    elif not f.registered:
        add("identity", ident, True, f"ID {f.transponder} not in {rules.registry_source}" if f.transponder
            else f"no transponder ID ({rules.registry_source})")
    elif not f.scheduled:
        add("identity", ident, True, f"{f.registry_id} is off schedule ({f.schedule_note})")
    else:
        add("identity", ident, True, f"{f.registry_id} is outside its zone ({f.zone_name})")

    hail = {
        "not_hailed": (None, "not needed"),
        "pending": (None, f"hailed {f.hail_age_s or 0:.0f} s ago, waiting"),
        "ok": (False, "answered and checked out"),
        "none": (True, f"no answer after {f.hail_age_s or 0:.0f} s"),
        "intermittent": (None, "intermittent answer"),
        "mismatch": (True, "answer does not match registration"),
        "unavailable": (None, "no compatible vehicle link; a reply was not expected"),
    }[f.hail]
    add("hail", "Answers the hail", *hail)

    add("improvised", "Improvised device", not f.improvised,
        f"device signature {pct(f.confidence)}" if f.improvised else "no device signature")
    a = f.approaching
    add("approach", "Closing on an asset", a is None,
        f"closing on {a.name}, {a.distance_m:.0f} m" if a else f"{f.speed_mps * MPS_TO_KN:.1f} kn, not closing")
    add("evasive", "Evading", not f.evasive, f.evasion_note if f.evasive else "steady after the hail"
        if f.hail_age_s is not None else "no investigation yet")
    near = {"low": True, "medium": None, "high": False}[f.consequence]
    add("consequence", "Near a critical asset", near, _dist(f))
    return checks


def _finish(c: _Ctx, outcome: str, rungs: list[str], reason: str, higher: str, lower: str,
            urgency: str | None = None, window_key: str | None = None, notice: str | None = None,
            drift: dict[str, Any] | None = None, window_s: float | None = None) -> Decision:
    f, rules = c.f, c.rules
    rungs = sorted(set(rungs), key=rung_index)
    top = rungs[-1]
    human = rules.requires_human(top)
    if human and c.track == "security":
        c.text_mode = "security"
        c.texts = rules.modes["security"]
    if urgency is None:
        urgency = "elevated" if human else "routine"
    windows = rules.windows
    if window_s is None:
        if window_key:
            window_s = getattr(windows, window_key)
        elif human:
            window_s = windows.urgent if urgency == "urgent" else windows.default
    focus = _focus(f)
    target = rules.handoff_target(c.text_mode)
    profile = rules.profile
    surface = profile.surface_channel if profile else rules.hail_channel
    acoustic = profile.acoustic_channel if profile else "compatible acoustic modem"
    contact_instruction = {
        "acoustic": f"Send an acoustic hail via {acoustic}; request ID.",
        "surface": f"Call the support vessel or operator on {surface}; request ID.",
        "unavailable": f"No compatible vehicle link; ask port traffic on {surface} to identify an operator.",
    }[f.hail_route]
    approval_role = ((profile.handoff_approver if top == "R5" else profile.hold_approver)
                     if profile and human else None)
    fmt = {
        "hail_channel": rules.hail_channel,
        "contact_instruction": contact_instruction,
        "hold_approver": profile.hold_approver if profile else "harbor watch officer",
        "handoff_approver": profile.handoff_approver if profile else "harbor watch officer",
        "look": min(c.mem.second_looks + 1, rules.loop.max_second_looks) or 1,
        "max_looks": rules.loop.max_second_looks,
        "vessels": ", ".join(f.traffic) if f.traffic else "nearby traffic",
        "asset": focus.name if focus else "the nearest berth",
        "operation": focus.operation if focus else "the nearest operation",
        "target": target,
    }
    actions = [c.texts.rungs[r].action.format(**fmt) for r in rungs]
    checks = build_checks(f, rules)
    up, down = c.above(rungs), c.below(rungs)
    return Decision(
        contact_id=f.contact_id, t=round(f.t, 1), clock=f.clock, track=c.track, outcome=outcome,
        rungs=rungs, rung=top, rung_names=[c.texts.rungs[r].name for r in rungs], path=list(c.path),
        reason=reason, checks=checks, ruled_out=[ch["label"] for ch in checks if ch["ruled_out"]],
        urgency=urgency, window_s=window_s if human else None, requires_human=human,
        recommendation=" ".join(actions),
        why_higher=f"Not {c.name(up)}: {higher}" if up else f"{c.name(top)} is the top rung. {higher}",
        why_lower=f"Not {c.name(down)}: {lower}" if down else f"{c.name(rungs[0])} is the floor. {lower}",
        notice=notice, label=f.label, label_text=display_label(f.label), confidence=f.confidence,
        category=f.category, consequence=f.consequence,
        nearest_asset=f.nearest_asset.as_dict() if f.nearest_asset else None,
        focus_asset=focus.as_dict() if focus else None,
        position=f.position, heading=round(f.heading), speed_kn=round(f.speed_mps * MPS_TO_KN, 1),
        size_m=f.size_m, zone=f.zone_name, registered=f.registered, registry_id=f.registry_id, hail=f.hail,
        hail_route=f.hail_route, approval_role=approval_role,
        look=c.mem.second_looks, max_looks=rules.loop.max_second_looks, traffic=list(f.traffic), drift=drift,
        scan_label=f.scan_label, trend=f.trend, closing_mps=f.closing_mps, cpa=f.cpa,
        consequence_basis=f.consequence_basis,
    )


def decide(f: Facts, mem: Memory, rules: Rules, mode: str = "security") -> Decision:
    if mem.first_seen_t is None:
        mem.first_seen_t = f.t
    if mode == "recovery" and is_recovery_target(f, rules):
        d = _recovery(_Ctx(f, mem, rules, "recovery", mode))
    else:
        d = _s0(_Ctx(f, mem, rules, "security", mode))
    latched = mem.latched
    if latched and d.severity() <= latched.severity():
        return replace(latched, **{k: getattr(d, k) for k in LIVE_FIELDS})
    if d.outcome in LATCHING:
        mem.latched = d
    return d


def _s0(c: _Ctx) -> Decision:
    f, thr = c.f, c.rules.thresholds
    if f.category == "non_vehicle" and f.confidence >= thr.non_vehicle_confidence:
        c.path.append("S0")
        return _finish(
            c, "non_vehicle", c.rules.ladder.non_vehicle,
            f"{display_label(f.label)} at {pct(f.confidence)}: not a vehicle. Logged, no action.",
            higher=f"already classified {display_label(f.label).lower()} at {pct(f.confidence)} "
                   f"(threshold {pct(thr.non_vehicle_confidence)}); another look adds nothing.",
            lower="it is still logged in the receipts.",
        )
    return _s1(c)


def _s1(c: _Ctx) -> Decision:
    f = c.f
    c.path.append("S1")
    if f.registered and f.scheduled and f.zone_authorized:
        return _s3(c, via="S1")
    return _s2(c)


def _s2(c: _Ctx) -> Decision:
    c.path.append("S2")
    if c.f.hail == "unavailable":
        return _s4(c)
    if c.mem.hailed_t is None:
        c.mem.hailed_t = c.f.t
    if c.f.hail == "not_hailed":
        c.f.hail, c.f.hail_age_s = "pending", 0.0
    if c.f.hail == "ok":
        return _s3(c, via="S2")
    return _s4(c)


def _s3(c: _Ctx, via: str) -> Decision:
    f, ladder = c.f, c.rules.ladder
    c.path.append("S3")
    if not f.consistent:
        if via == "S5":
            return _unknown(c, f"classified {display_label(f.label).lower()} but {f.consistency_note}")
        return _s4(c)
    who = _who(f)
    if via == "S1":
        reason = f"{who}: registered, on schedule, in its authorized zone."
        higher = "it is registered, on schedule and in its own zone. Hailing it adds radio noise."
    elif via == "S2":
        reason = f"{who} answered the hail and checks out ({f.consistency_note})."
        higher = "it answered the hail and its answer checks out."
    else:
        reason = f"Classified {display_label(f.label).lower()} at {pct(f.confidence)} and {f.consistency_note}."
        higher = f"it classifies as {display_label(f.label).lower()} at {pct(f.confidence)} and behaves like one."
    lower = "it is still logged."
    if f.zone_critical:
        notice = f"{who} is inside {f.zone_name}. Informational only."
        return _finish(c, "identity_ok_critical", ladder.identity_ok_critical, reason + f" Inside {f.zone_name}.",
                       higher + " A critical zone earns a notice, not an action.", lower, notice=notice)
    return _finish(c, "identity_ok_noncritical", ladder.identity_ok_noncritical, reason, higher, lower)


def _s4(c: _Ctx) -> Decision:
    f, ladder = c.f, c.rules.ladder
    c.path.append("S4")
    top = "a person decides how it is handled; physical response is out of scope."
    if f.improvised:
        return _finish(c, "threat", ladder.threat,
                       f"Improvised-device signature ({pct(f.confidence)}), {_dist(f)}.",
                       top, "a device signature needs a person now, not a paused berth.", urgency="urgent")
    if f.hostile:
        return _finish(c, "threat", ladder.threat, f"Flagged hostile, {_dist(f)}.",
                       top, "a hostile flag needs a person now.", urgency="urgent")
    if f.approaching:
        a = f.approaching
        hail_state = ("no compatible vehicle link" if f.hail == "unavailable" else
                      "hail pending" if f.hail == "pending" else "no answer to the hail")
        return _finish(c, "threat", ladder.threat,
                       f"Closing on {a.name} at {f.speed_mps * MPS_TO_KN:.1f} kn, {a.distance_m:.0f} m out, " +
                       f"with {hail_state}.",
                       top, f"it is closing on {a.name}; holding one operation will not stop it arriving.",
                       urgency="urgent")
    return _s5(c)


def _s5(c: _Ctx) -> Decision:
    f, rules = c.f, c.rules
    c.path.append("S5")
    if f.evasive:
        return _finish(c, "evasive", rules.ladder.evasive, f"Evading the investigation: {f.evasion_note}.",
                       "a person decides how it is handled; physical response is out of scope.",
                       f"holding assumes it stays put; it {f.evasion_note}.", urgency="urgent")
    d = _classify_branch(c)
    cap = rules.ladder.awaiting_hail
    if f.hail == "pending" and rung_index(d.rung) > max(rung_index(r) for r in cap):
        return _finish(c, "awaiting_hail", cap,
                       f"Hailed {f.hail_age_s or 0:.0f} s ago; giving it {rules.hail.timeout_s:.0f} s to answer "
                       f"before escalating. {_cap(_dist(f))}.",
                       f"the hail gets {rules.hail.timeout_s:.0f} s to be answered before anything heavier.",
                       "it has not been identified yet.")
    return d


def _classify_branch(c: _Ctx) -> Decision:
    f, rules = c.f, c.rules
    confident = f.confidence >= rules.thresholds.classify_confidence
    if confident and f.category in ("research", "commercial"):
        return _s3(c, via="S5")
    if confident and f.category == "military":
        return _finish(c, "military", rules.ladder.military,
                       f"Classified {display_label(f.label).lower()} at {pct(f.confidence)}, unannounced, {_dist(f)}.",
                       "closing the harbor is the bang we design against.",
                       "asking or slowing traffic does not answer who is operating it.",
                       window_key="hold_handoff")
    return _unknown(c)


def _unknown(c: _Ctx, note: str | None = None) -> Decision:
    f, rules = c.f, c.rules
    if note:
        lead = _cap(note)
    elif f.label == "unknown":
        lead = f"Unidentified contact ({pct(f.confidence)})"
    else:
        lead = (f"Possible {display_label(f.label).lower()} at {pct(f.confidence)}, "
                f"under the {pct(rules.thresholds.classify_confidence)} bar")
    asset = f.nearest_asset
    band = rules.band_for(asset.kind) if asset else rules.consequence.default
    hail_gap = "no compatible vehicle link" if f.hail == "unavailable" else "no answer to the hail"
    if f.consequence == "high":
        op = _focus(f)
        return _finish(c, "unknown_high", rules.ladder.unknown_high,
                       f"{lead}, {hail_gap}, {_dist(f)}" + (f" during {op.operation}." if op else "."),
                       "pausing one operation is the gentlest step that removes the risk; "
                       "closing the harbor is the bang.",
                       f"slowing traffic leaves {op.operation if op else 'operations'} running "
                       f"{asset.distance_m:.0f} m from an unidentified vehicle." if asset else "the risk stays.",
                       window_key="hold_handoff")
    if f.consequence == "medium":
        if f.traffic:
            return _finish(c, "unknown_medium_traffic", rules.ladder.unknown_medium_traffic,
                           f"{lead}, {_dist(f)}; {', '.join(f.traffic)} within {rules.traffic_radius_m:.0f} m.",
                           f"holding needs high consequence; it is {asset.distance_m:.0f} m out "
                           f"(high starts at {band.high_m:.0f} m).",
                           f"asking alone leaves {', '.join(f.traffic)} uninformed.")
        inside = (f"its course passes {f.cpa['distance_m']} m from {asset.name} within {f.cpa['in_s']} s."
                  if f.consequence_basis == "cpa" and f.cpa else
                  f"it is inside the {band.medium_m:.0f} m medium band of {asset.name}.")
        return _finish(c, "unknown_medium_quiet", rules.ladder.unknown_medium_quiet,
                       f"{lead}, {_dist(f)}. No traffic nearby; asking for ID.",
                       f"no vessels within {rules.traffic_radius_m:.0f} m to advise, and holding needs "
                       f"high consequence (within {band.high_m:.0f} m).",
                       inside)
    return _low_loop(c, lead, band)


def _low_loop(c: _Ctx, lead: str, band) -> Decision:
    f, rules, mem = c.f, c.rules, c.mem
    loop = rules.loop
    base = rules.ladder.unknown_low
    far = f"nearest asset {f.nearest_asset.name} is {f.nearest_asset.distance_m:.0f} m away" \
        if f.nearest_asset else "no asset nearby"
    if "R1" not in base:
        return _finish(c, "unknown_low", base, f"{lead}, {far}. Low consequence.",
                       f"low consequence; {far}. Confidence alone never escalates.",
                       "the ladder maps low consequence here.")
    if mem.escalated or mem.second_looks >= loop.max_second_looks:
        mem.escalated = True
        rungs = _shift(base, loop.escalate_by)
        return _finish(c, "unknown_low_escalated", rungs,
                       f"Still unidentified after {mem.second_looks} second look"
                       f"{'s' if mem.second_looks != 1 else ''}; loop cap reached, up one rung.",
                       f"consequence is still low; {far} (medium starts at {band.medium_m:.0f} m).",
                       f"the loop cap is {loop.max_second_looks}; it never loops forever.")
    if mem.next_look_t is None:
        mem.next_look_t = f.t + loop.interval_s
    elif f.t >= mem.next_look_t:
        mem.second_looks += 1
        mem.next_look_t = f.t + loop.interval_s
    done = (f"second look 1 of {loop.max_second_looks} scheduled" if mem.second_looks == 0
            else f"{mem.second_looks} of {loop.max_second_looks} second looks done")
    return _finish(c, "unknown_low", base,
                   f"{lead}, {far}. Low consequence: {done}.",
                   f"asking needs medium consequence; {far} (medium starts at {band.medium_m:.0f} m). "
                   f"Confidence alone never escalates.",
                   "it has not been identified; " + ("no compatible vehicle link exists."
                   if f.hail == "unavailable" else "it has not answered the hail."))


def is_recovery_target(f: Facts, rules: Rules) -> bool:
    entry = rules.registry_entry(rules.recovery.lost_vehicle_id)
    if entry is None or f.improvised or f.hostile or f.evasive:
        return False
    if f.transponder:
        return f.transponder == entry.id
    if f.signature == entry.signature:
        return True
    return f.category == "research" and abs(f.size_m - entry.size_m) <= rules.consistency.size_tolerance_m


def drift_estimate(f: Facts, rules: Rules) -> dict[str, Any]:
    horizon = rules.recovery.drift_horizon_s
    end = project(f.position, f.heading, f.speed_mps, horizon)
    current = resolve_zone(rules, f.position)
    eta = None
    for step in range(10, int(horizon) + 1, 10):
        p = project(f.position, f.heading, f.speed_mps, step)
        zone = resolve_zone(rules, p)
        if zone and zone.critical and (current is None or zone.id != current.id):
            eta = {"zone": zone.name, "seconds": step}
            break
    hazards = sorted((distance_to(end, a.shape), a.name) for a in rules.assets if a.active)
    return {
        "heading": round(f.heading), "speed_kn": round(f.speed_mps * MPS_TO_KN, 2),
        "horizon_s": horizon, "projected": [round(end[0]), round(end[1])], "eta_critical": eta,
        "nearest_hazard_at_horizon": {"name": hazards[0][1], "distance_m": round(hazards[0][0])} if hazards else None,
    }


def _recovery(c: _Ctx) -> Decision:
    f, rules, mem = c.f, c.rules, c.mem
    rec, loop = rules.recovery, rules.loop
    entry = rules.registry_entry(rec.lost_vehicle_id)
    c.path.append("M1")
    if mem.hailed_t is None:
        mem.hailed_t = f.t
    sig_match = f.signature == entry.signature
    id_match = f.transponder == entry.id and f.hail in ("ok", "intermittent")
    confirmed = id_match or (f.confidence >= rec.confirm_confidence and (sig_match or f.category == "research"))
    evidence = "modem answered with its ID" if id_match else \
        "sonar signature matches" if sig_match else "size and class match"
    if not confirmed:
        c.path.append("M2")
        if mem.second_looks >= loop.max_second_looks:
            return _finish(c, "rec_possible_exhausted", rec.ladder.possible_exhausted,
                           f"Possible {entry.id} ({evidence}, {pct(f.confidence)}); re-scans used up, pinging.",
                           f"confirmation needs {pct(rec.confirm_confidence)}; we have {pct(f.confidence)}.",
                           f"re-scans are capped at {loop.max_second_looks}; pinging is the next gentlest step.")
        if mem.next_look_t is None:
            mem.next_look_t = f.t + loop.interval_s
        elif f.t >= mem.next_look_t:
            mem.second_looks += 1
            mem.next_look_t = f.t + loop.interval_s
        done = (f"re-scan 1 of {loop.max_second_looks} scheduled" if mem.second_looks == 0
                else f"{mem.second_looks} of {loop.max_second_looks} re-scans done")
        return _finish(c, "rec_possible", rec.ladder.possible,
                       f"Possible {entry.id}: {evidence} at {pct(f.confidence)}; {done}.",
                       f"pinging waits until re-scans are used up ({mem.second_looks} of {loop.max_second_looks}).",
                       f"{evidence}; it could be {entry.id}.")
    c.path.append("M3")
    drift = drift_estimate(f, rules)
    eta = drift["eta_critical"]
    drift_txt = f"drifting {drift['speed_kn']} kn at {drift['heading']}°"
    if eta:
        drift_txt += f", reaches {eta['zone']} in ~{eta['seconds'] // 60} min"
    common = dict(window_s=rec.window_s, drift=drift)
    found = f"Found {entry.id} ({evidence}, {pct(f.confidence)}), {drift_txt}."
    if f.consequence == "high":
        op = _focus(f)
        return _finish(c, "rec_confirmed_hazard", rec.ladder.confirmed_hazard, found + f" {_dist(f)}.",
                       "recovery is a boat and a person, not a harbor closure.",
                       f"it is {_dist(f)}; {op.operation if op else 'operations'} should pause until it is out.",
                       urgency="elevated", **common)
    if f.traffic:
        return _finish(c, "rec_confirmed_traffic", rec.ladder.confirmed_traffic,
                       found + f" {', '.join(f.traffic)} nearby.",
                       f"holding a lane only if it drifts into an operation; {_dist(f)}.",
                       f"{', '.join(f.traffic)} are within {rules.traffic_radius_m:.0f} m of it.",
                       urgency="routine", **common)
    return _finish(c, "rec_confirmed", rec.ladder.confirmed, found,
                   f"holding a lane only if it drifts into an operation; {_dist(f)}.",
                   "the owner needs the fix now, while it is still close.", urgency="routine", **common)


def advise_decision(f: Facts, mem: Memory, rules: Rules, mode: str, d: Decision, raise_by: int,
                    second_look: bool, note: str) -> Decision:
    c = _Ctx(f, mem, rules, d.track, mode)
    c.path = list(d.path) + ["AI"]
    rungs, outcome = list(d.rungs), d.outcome
    loop = rules.loop
    extra = raise_by
    if rung_index(d.rung) < rung_index("R1") and (raise_by > 0 or second_look):
        if mem.second_looks >= loop.max_second_looks:
            rungs, outcome = _shift(["R1"], loop.escalate_by), "advisor_look_escalated"
        else:
            if mem.next_look_t is None:
                mem.next_look_t = f.t + loop.interval_s
            elif f.t >= mem.next_look_t:
                mem.second_looks += 1
                mem.next_look_t = f.t + loop.interval_s
            rungs, outcome = ["R1"], "advisor_second_look"
        extra = max(0, raise_by - 1)
    if extra > 0:
        rungs = _shift(rungs, extra)
        if outcome == d.outcome:
            outcome = f"{d.outcome}_raised"
    if rung_index(rungs[-1]) <= rung_index(d.rung) and outcome == d.outcome:
        return d
    return _finish(c, outcome, rungs, f"{d.reason} Advisor: {note}",
                   "the advisor may raise a contact, but anything further needs a hard trigger or a person.",
                   f"the advisor flagged it: {note}")

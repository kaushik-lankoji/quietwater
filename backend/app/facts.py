from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .classifier import Classification
from .geometry import angle_diff, bearing, contains, distance_to, heading_vector, nearest_point
from .rules import Rules

LEVELS = ("low", "medium", "high")
MPS_TO_KN = 1.943844


@dataclass(frozen=True)
class AssetRef:
    id: str
    name: str
    kind: str
    operation: str
    distance_m: float

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "kind": self.kind, "operation": self.operation,
                "distance_m": round(self.distance_m)}


@dataclass
class Facts:
    contact_id: str
    t: float
    clock: str
    position: tuple[float, float]
    heading: float
    speed_mps: float
    size_m: float
    signature: str
    transponder: str | None
    label: str
    confidence: float
    category: str
    registered: bool = False
    registry_id: str | None = None
    scheduled: bool = False
    schedule_note: str = ""
    zone_id: str | None = None
    zone_name: str = "open water"
    zone_critical: bool = False
    zone_authorized: bool = False
    hail: str = "not_hailed"
    hail_route: str = "acoustic"
    hail_age_s: float | None = None
    consistent: bool = True
    consistency_note: str = ""
    consequence: str = "low"
    nearest_asset: AssetRef | None = None
    approaching: AssetRef | None = None
    hostile: bool = False
    evasive: bool = False
    evasion_note: str = ""
    improvised: bool = False
    traffic: list[str] = field(default_factory=list)
    trail: list[tuple[float, float, float, float, float]] = field(default_factory=list)
    scan_label: str = "unknown"
    trend: str = "new"
    closing_mps: float = 0.0
    cpa: dict[str, Any] | None = None
    consequence_basis: str = "distance"


def clock_at(start: str, t: float) -> str:
    h, m = (int(p) for p in start.split(":"))
    total = int(h * 3600 + m * 60 + t) % 86400
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _minutes(hhmm: str) -> int:
    h, m = (int(p) for p in hhmm.split(":")[:2])
    return h * 60 + m


def in_window(clock: str, start: str, end: str) -> bool:
    now, a, b = _minutes(clock), _minutes(start), _minutes(end)
    return a <= now < b if a <= b else now >= a or now < b


def resolve_zone(rules: Rules, p: tuple[float, float]):
    return next((z for z in rules.zones if contains(z.shape, p)), None)


def assess_consequence(rules: Rules, p: tuple[float, float]) -> tuple[str, AssetRef | None]:
    best_level, best_ref = 0, None
    nearest_ref = None
    for asset in rules.assets:
        if not asset.active:
            continue
        d = distance_to(p, asset.shape)
        band = rules.band_for(asset.kind)
        level = 2 if d <= band.high_m else 1 if d <= band.medium_m else 0
        ref = AssetRef(asset.id, asset.name, asset.kind, asset.operation, d)
        if nearest_ref is None or d < nearest_ref.distance_m:
            nearest_ref = ref
        if level > best_level or (level == best_level and level > 0 and d < best_ref.distance_m):
            best_level, best_ref = level, ref
    return LEVELS[best_level], best_ref or nearest_ref


def _level(rules: Rules, kind: str, d: float) -> int:
    band = rules.band_for(kind)
    return 2 if d <= band.high_m else 1 if d <= band.medium_m else 0


def closest_approach(rules: Rules, p: tuple[float, float], heading: float, speed: float) -> dict[str, Any] | None:
    cfg = rules.consequence.cpa
    if cfg.horizon_s <= 0 or speed <= 0:
        return None
    steps = int(cfg.horizon_s // cfg.step_s)
    path = [project(p, heading, speed, k * cfg.step_s) for k in range(steps + 1)]
    best = None
    for asset in rules.assets:
        if not asset.active:
            continue
        d, k = min((distance_to(q, asset.shape), k) for k, q in enumerate(path))
        level = _level(rules, asset.kind, d)
        rank = (level, -d)
        if best is None or rank > best[0]:
            best = (rank, {"asset": AssetRef(asset.id, asset.name, asset.kind, asset.operation,
                                              distance_to(p, asset.shape)),
                           "distance_m": round(d), "in_s": round(k * cfg.step_s), "level": LEVELS[level]})
    return best[1] if best else None


def assess_trend(rules: Rules, trail, position: tuple[float, float], speed: float, now: float,
                 asset: AssetRef | None) -> tuple[str, float]:
    cfg = rules.trend
    window = [s for s in trail if s[0] >= now - cfg.window_s]
    if len(window) < 3 or window[-1][0] - window[0][0] < cfg.window_s * 0.9:
        return "new", 0.0
    turned = sum(angle_diff(a[3], b[3]) for a, b in zip(window, window[1:], strict=False))
    shape = next((a.shape for a in rules.assets if asset and a.id == asset.id), None)
    rate = 0.0
    if shape is not None:
        span = now - window[0][0]
        rate = (distance_to(position, shape) - distance_to((window[0][1], window[0][2]), shape)) / span
    if turned >= cfg.loiter_turn_deg or speed <= cfg.loiter_speed_mps:
        return "loitering", round(rate, 3)
    if rate <= -cfg.closing_mps:
        return "closing", round(rate, 3)
    if rate >= cfg.closing_mps:
        return "leaving", round(rate, 3)
    return "steady", round(rate, 3)


def coarse_label(rules: Rules, label: str, category: str, confidence: float) -> str:
    if category == "non_vehicle":
        return "marine_life" if label == "biologic" else "debris"
    if category in ("research", "commercial") and confidence >= rules.thresholds.classify_confidence:
        return "known_vehicle"
    return "unknown"


def find_approach(rules: Rules, p: tuple[float, float], heading: float, speed: float) -> AssetRef | None:
    cfg = rules.approach
    if speed < cfg.min_speed_mps:
        return None
    hits = []
    for asset in rules.assets:
        if not asset.active:
            continue
        d = distance_to(p, asset.shape)
        if d > cfg.radius_m:
            continue
        if d > 0 and angle_diff(heading, bearing(p, nearest_point(p, asset.shape))) > cfg.cone_deg:
            continue
        hits.append(AssetRef(asset.id, asset.name, asset.kind, asset.operation, d))
    return min(hits, key=lambda a: a.distance_m) if hits else None


def detect_evasion(rules: Rules, trail, hailed_t: float | None, now: float) -> tuple[bool, str]:
    if hailed_t is None or now <= hailed_t:
        return False, ""
    cfg = rules.evasion
    window = [s for s in trail if s[0] >= max(hailed_t, now - cfg.window_s)]
    if len(window) < 3:
        return False, ""
    turned = sum(angle_diff(a[3], b[3]) for a, b in zip(window, window[1:], strict=False))
    if turned >= cfg.turn_deg:
        return True, f"turned {turned:.0f}° in {window[-1][0] - window[0][0]:.0f} s after the hail"
    before = [s for s in trail if s[0] <= hailed_t]
    base = before[-1][4] if before else window[0][4]
    peak = max(s[4] for s in window)
    if base > 0.05 and peak >= base * cfg.speed_jump:
        return True, f"sped up ×{peak / base:.1f} after the hail"
    return False, ""


def check_consistency(rules: Rules, entry, label: str, size: float, speed: float, signature: str,
                      hail: str) -> tuple[bool, str]:
    problems = []
    if hail == "mismatch":
        problems.append("hail answer does not match registration")
    margin = rules.consistency.speed_margin
    if entry is not None:
        if abs(size - entry.size_m) > rules.consistency.size_tolerance_m:
            problems.append(f"size {size:.1f} m vs registered {entry.size_m:.1f} m")
        if signature != entry.signature:
            problems.append("sonar signature differs from registration")
        profile = rules.class_profiles.get(entry.vehicle_type)
    else:
        profile = rules.class_profiles.get(label)
    if profile and speed > profile.max_speed_mps * margin:
        problems.append(f"{speed * MPS_TO_KN:.1f} kn is too fast for its class")
    if problems:
        return False, "; ".join(problems)
    return True, "matches registration" if entry else "behaves like its class"


def derive_facts(*, contact_id: str, t: float, clock: str, position: tuple[float, float], heading: float,
                 speed_mps: float, size_m: float, signature: str, transponder: str | None,
                 classification: Classification, hail: str, hailed_t: float | None, hostile: bool,
                 scripted_evasive: bool, trail, rules: Rules, hail_route: str = "acoustic") -> Facts:
    category = rules.classes.get(classification.label, rules.classes["unknown"])
    entry = rules.registry_entry(transponder)
    zone = resolve_zone(rules, position)
    scheduled, schedule_note = False, ""
    if entry:
        windows = ", ".join(f"{w.start}-{w.end}" for w in entry.schedule) or "none"
        scheduled = any(in_window(clock, w.start, w.end) for w in entry.schedule)
        schedule_note = f"window {windows}"
    consistent, consistency_note = check_consistency(
        rules, entry, classification.label, size_m, speed_mps, signature, hail)
    consequence, nearest = assess_consequence(rules, position)
    basis = "distance"
    cpa = None
    if category != "non_vehicle":
        cpa = closest_approach(rules, position, heading, speed_mps)
        cap = LEVELS.index(rules.consequence.cpa.raise_to)
        if cpa and min(LEVELS.index(cpa["level"]), cap) > LEVELS.index(consequence):
            consequence, nearest, basis = LEVELS[min(LEVELS.index(cpa["level"]), cap)], cpa["asset"], "cpa"
    trend, closing = assess_trend(rules, trail, position, speed_mps, t, (cpa or {}).get("asset") or nearest)
    evasive, evasion_note = detect_evasion(rules, trail, hailed_t, t)
    if scripted_evasive and not evasive:
        evasive, evasion_note = True, "evading the investigation"
    radius = rules.traffic_radius_m
    traffic = [v.name for v in rules.traffic if math.dist(position, (v.x, v.y)) <= radius]
    return Facts(
        contact_id=contact_id, t=t, clock=clock, position=position, heading=heading, speed_mps=speed_mps,
        size_m=size_m, signature=signature, transponder=transponder, label=classification.label,
        confidence=classification.confidence, category=category,
        registered=entry is not None, registry_id=entry.id if entry else None,
        scheduled=scheduled, schedule_note=schedule_note,
        zone_id=zone.id if zone else None, zone_name=zone.name if zone else "open water",
        zone_critical=bool(zone and zone.critical),
        zone_authorized=bool(entry and zone and zone.id in entry.authorized_zones),
        hail=hail, hail_route=hail_route, hail_age_s=(t - hailed_t) if hailed_t is not None else None,
        consistent=consistent, consistency_note=consistency_note,
        consequence=consequence, nearest_asset=nearest,
        approaching=find_approach(rules, position, heading, speed_mps),
        hostile=hostile, evasive=evasive, evasion_note=evasion_note,
        improvised=category == "improvised" and classification.confidence >= rules.thresholds.improvised_confidence,
        traffic=traffic, trail=list(trail),
        scan_label=coarse_label(rules, classification.label, category, classification.confidence),
        trend=trend, closing_mps=closing,
        cpa={k: (v.as_dict() if isinstance(v, AssetRef) else v) for k, v in cpa.items()} if cpa else None,
        consequence_basis=basis,
    )


def project(position: tuple[float, float], heading: float, speed: float, seconds: float) -> tuple[float, float]:
    vx, vy = heading_vector(heading)
    return position[0] + vx * speed * seconds, position[1] + vy * speed * seconds

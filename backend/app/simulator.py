from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .geometry import bearing, heading_vector, point_in_polygon

TRAIL_LEN = 80


@dataclass
class SimContact:
    id: str
    archetype: str
    truth: str
    x: float
    y: float
    heading: float
    speed: float
    size_m: float
    signature: str
    motion: str
    hail: str
    hail_route: str = "acoustic"
    transponder: str | None = None
    hail_delay_s: float = 4.0
    hostile: bool = False
    evasive_flag: bool = False
    evade_on_hail: bool = False
    evade_delay_s: float = 6.0
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    loop: bool = False
    label_track: tuple[dict[str, Any], ...] = ()
    spawn_t: float = 0.0
    despawn_t: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    hailed_t: float | None = None
    evading: bool = False
    wp_index: int = 0
    base_speed: float = 0.0
    next_turn_t: float = 0.0
    anchor: tuple[float, float] = (0.0, 0.0)
    trail: deque = field(default_factory=lambda: deque(maxlen=TRAIL_LEN))
    rng: random.Random = field(default_factory=random.Random)

    def hail_status(self, t: float, timeout_s: float) -> str:
        if self.hail_route == "unavailable":
            return "unavailable"
        if self.hailed_t is None:
            return "not_hailed"
        age = t - self.hailed_t
        if self.hail in ("ok", "mismatch", "intermittent") and age >= self.hail_delay_s:
            return self.hail
        return "pending" if age < timeout_s else "none"


def is_water(harbor: dict[str, Any], p: tuple[float, float]) -> bool:
    b = harbor["bounds"]
    if not (0 <= p[0] <= b["w"] and 0 <= p[1] <= b["h"]):
        return False
    if any(point_in_polygon(p, poly) for poly in harbor["land"]):
        return False
    return not any(pr["x"] <= p[0] <= pr["x"] + pr["w"] and pr["y"] <= p[1] <= pr["y"] + pr["h"]
                   for pr in harbor.get("piers", []))


class Simulator:
    def __init__(self, scenario: dict[str, Any], catalog: dict[str, Any], harbor: dict[str, Any],
                 seed: int | None = None):
        self.scenario = scenario
        self.catalog = catalog
        self.harbor = harbor
        self.seed = scenario.get("seed", 0) if seed is None else seed
        self.rng = random.Random(self.seed)
        self.t = 0.0
        self.active: dict[str, SimContact] = {}
        self.departed: list[str] = []
        specs = list(scenario.get("contacts", []))
        if scenario.get("generator"):
            specs += self._generate(scenario["generator"])
        self.pending = sorted((self._build(s) for s in specs), key=lambda c: c.spawn_t)
        current = catalog.get("current", {})
        self.current_heading = float(current.get("heading", 0))
        self.current_speed = float(current.get("speed_mps", 0))

    def _build(self, spec: dict[str, Any]) -> SimContact:
        arch = dict(self.catalog["archetypes"][spec["archetype"]])
        merged = {**arch, **spec}
        if merged.get("hail_route", "acoustic") not in ("acoustic", "surface", "unavailable"):
            raise ValueError("hail_route must be acoustic, surface, or unavailable")
        x, y = merged["start"]
        heading = merged.get("heading")
        if heading is None:
            choices = merged.get("heading_choices")
            heading = self.rng.choice(choices) if choices else self.rng.uniform(0, 360)
        wps = [tuple(p) for p in merged.get("waypoints", [])]
        motion = merged.get("motion", "straight")
        if wps and "motion" not in spec and motion != "waypoints":
            motion = "waypoints"
        c = SimContact(
            id=spec["id"], archetype=spec["archetype"], truth=merged["truth"], x=float(x), y=float(y),
            heading=float(heading), speed=float(merged.get("speed_mps", 0.3)), size_m=float(merged["size_m"]),
            signature=merged["signature"], motion=motion, hail=merged.get("hail", "none"),
            hail_route=merged.get("hail_route", "acoustic"),
            transponder=merged.get("transponder"), hail_delay_s=float(merged.get("hail_delay_s", 4)),
            hostile=bool(merged.get("hostile", False)), evasive_flag=bool(merged.get("evasive", False)),
            evade_on_hail=bool(merged.get("evade_on_hail", False)),
            evade_delay_s=float(merged.get("evade_delay_s", 6)),
            waypoints=wps, loop=bool(merged.get("loop", False)),
            label_track=tuple(merged.get("label_track", ())),
            spawn_t=float(merged.get("spawn_t", 0)), despawn_t=merged.get("despawn_t"),
            events=sorted(merged.get("events", []), key=lambda e: e["t"]),
            rng=random.Random(f"{self.seed}:{spec['id']}"),
        )
        c.base_speed = c.speed
        c.anchor = (c.x, c.y)
        if wps and motion == "waypoints":
            c.heading = bearing((c.x, c.y), wps[0])
        return c

    def _generate(self, gen: dict[str, Any]) -> list[dict[str, Any]]:
        mix = gen["mix"]
        names, weights = list(mix), list(mix.values())
        regions = gen.get("regions", {})
        prefix = gen.get("prefix", "G")
        out = []
        for i in range(int(gen["count"])):
            arch = self.rng.choices(names, weights)[0]
            x, y = self._random_point(regions.get(arch))
            spec: dict[str, Any] = {"id": f"{prefix}-{i + 1:03d}", "archetype": arch, "start": [x, y],
                                    "spawn_t": round(self.rng.uniform(0, gen.get("spawn_window_s", 20)), 1)}
            if not self.catalog["archetypes"][arch].get("heading_choices"):
                cx = self.harbor["spawn_area"]["x"] + self.harbor["spawn_area"]["w"] / 2
                cy = self.harbor["spawn_area"]["y"] + self.harbor["spawn_area"]["h"] / 2
                spec["heading"] = (bearing((x, y), (cx, cy)) + self.rng.uniform(-60, 60)) % 360
            out.append(spec)
        return out

    def _random_point(self, regions: list[list[float]] | None) -> tuple[float, float]:
        areas = regions or [[self.harbor["spawn_area"][k] for k in ("x", "y", "w", "h")]]
        for _ in range(200):
            x0, y0, w, h = self.rng.choice(areas)
            p = (round(x0 + self.rng.uniform(0, w)), round(y0 + self.rng.uniform(0, h)))
            if self.is_water(p):
                return p
        return areas[0][0] + areas[0][2] / 2, areas[0][1] + areas[0][3] / 2

    def is_water(self, p: tuple[float, float]) -> bool:
        return is_water(self.harbor, p)

    def step(self, dt: float) -> None:
        self.t = round(self.t + dt, 3)
        while self.pending and self.pending[0].spawn_t <= self.t:
            c = self.pending.pop(0)
            c.trail.append((self.t, c.x, c.y, c.heading, c.speed))
            self.active[c.id] = c
        for c in list(self.active.values()):
            self._events(c)
            self._steer(c, dt)
            self._move(c, dt)
            c.trail.append((self.t, c.x, c.y, c.heading, c.speed))
            b = self.harbor["bounds"]
            gone = not (-50 <= c.x <= b["w"] + 50 and -50 <= c.y <= b["h"] + 50)
            if gone or (c.despawn_t is not None and self.t >= c.despawn_t):
                del self.active[c.id]
                self.departed.append(c.id)

    def _events(self, c: SimContact) -> None:
        while c.events and c.events[0]["t"] <= self.t:
            for key, value in c.events.pop(0).get("set", {}).items():
                if key == "speed_mps":
                    c.speed = c.base_speed = float(value)
                elif key == "evasive":
                    c.evasive_flag = bool(value)
                else:
                    setattr(c, key, value)

    def _steer(self, c: SimContact, dt: float) -> None:
        if c.evade_on_hail and c.hailed_t is not None and self.t >= c.hailed_t + c.evade_delay_s:
            c.evading = True
        if c.evading:
            c.speed = c.base_speed * 2
            if self.t >= c.next_turn_t:
                c.heading = (c.heading + c.rng.choice((-1, 1)) * c.rng.uniform(50, 100)) % 360
                c.next_turn_t = self.t + c.rng.uniform(3, 5)
            return
        if c.motion == "drift":
            c.heading = self.current_heading
            c.speed = max(c.base_speed, self.current_speed)
        elif c.motion == "wander":
            if self.t >= c.next_turn_t:
                c.heading = (c.heading + c.rng.uniform(-25, 25)) % 360
                c.next_turn_t = self.t + c.rng.uniform(6, 12)
        elif c.motion == "loiter":
            c.heading = (c.heading + 3 * dt) % 360
        elif c.motion == "waypoints" and c.waypoints:
            if c.wp_index >= len(c.waypoints):
                c.motion = "loiter"
                return
            target = c.waypoints[c.wp_index]
            if math.dist((c.x, c.y), target) < max(8.0, c.speed * dt * 1.5):
                c.wp_index += 1
                if c.wp_index >= len(c.waypoints) and c.loop:
                    c.wp_index = 0
                if c.wp_index < len(c.waypoints):
                    target = c.waypoints[c.wp_index]
            want = bearing((c.x, c.y), target)
            turn = max(-20 * dt, min(20 * dt, ((want - c.heading + 180) % 360) - 180))
            c.heading = (c.heading + turn) % 360

    def _move(self, c: SimContact, dt: float) -> None:
        vx, vy = heading_vector(c.heading)
        nx, ny = c.x + vx * c.speed * dt, c.y + vy * c.speed * dt
        if self.is_water((nx, ny)) or not self._inside((nx, ny)):
            c.x, c.y = nx, ny
            return
        for delta in (30, -30, 60, -60, 90, -90, 135, -135, 180):
            h = (c.heading + delta) % 360
            vx, vy = heading_vector(h)
            p = (c.x + vx * c.speed * dt, c.y + vy * c.speed * dt)
            if self.is_water(p):
                c.heading = h
                c.x, c.y = p
                return

    def _inside(self, p: tuple[float, float]) -> bool:
        b = self.harbor["bounds"]
        return 0 <= p[0] <= b["w"] and 0 <= p[1] <= b["h"]

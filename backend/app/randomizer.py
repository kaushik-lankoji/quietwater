from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Iterator
from typing import Any

from .simulator import is_water


def randomize(template: dict[str, Any], seed: int, catalog: dict[str, Any], harbor: dict[str, Any]) -> dict[str, Any]:
    spec = template["randomize"]
    cfg = catalog["randomizer"]
    kind = cfg[spec["kind"]]
    slots, regions = cfg["slots"], cfg["regions"]
    rng = random.Random(f"randomize:{spec['kind']}:{seed}")
    radius_lo, radius_hi = cfg["coverage_radius_m"]
    radius = rng.randrange(radius_lo // 50, radius_hi // 50 + 1) * 50
    traffic = rng.choices(cfg["traffic"], weights=[item["weight"] for item in cfg["traffic"]])[0]
    count = rng.randint(*traffic["contacts"])
    reachable = {name: list(_reachable_variants(slot, regions, harbor, radius))
                 for name, slot in slots.items()}
    eligible = {name for name, variants in reachable.items() if variants}

    picks = []
    for group in kind["required"]:
        options = [name for name in group if name in eligible]
        if len(picks) < count and options:
            picks.append(rng.choice(options))
    used = Counter(picks)
    while len(picks) < count:
        open_ = {n: w for n, w in kind["fill"].items()
                 if n in eligible and used[n] < slots[n].get("max", count)}
        if not open_:
            break
        name = rng.choices(list(open_), list(open_.values()))[0]
        picks.append(name)
        used[name] += 1
    rng.shuffle(picks)

    prefix = spec.get("prefix", "R")
    contacts = [_contact(f"{prefix}-{i + 1:02d}", slots[name], reachable[name], regions, rng, harbor, catalog, radius)
                for i, name in enumerate(picks)]
    out = {k: v for k, v in template.items() if k != "randomize"}
    description = f"Seed {seed}: {traffic['name'].lower()}, {len(contacts)} contacts across a {radius} m watch radius."
    out.update(seed=seed, contacts=contacts, coverage_radius_m=radius, traffic_level=traffic["name"],
               water_area_km2=water_area_km2(harbor, radius),
               description=f"{description} {template.get('description', '')}".strip())
    if spec.get("clock_starts"):
        out["clock_start"] = rng.choice(spec["clock_starts"])
    return out


def _contact(cid: str, slot: dict[str, Any], variants: list[dict[str, Any]],
             regions: dict[str, Any], rng: random.Random, harbor: dict[str, Any],
             catalog: dict[str, Any], radius: int) -> dict[str, Any]:
    s = {k: v for k, v in slot.items() if k != "variants"}
    if slot.get("variants"):
        s.update(rng.choice(variants))
    archetype = s["archetype"]
    base = catalog["archetypes"][archetype]
    area = regions[s["region"]]
    x, y = _point(area, rng, harbor, radius)
    c: dict[str, Any] = {"id": cid, "archetype": archetype, "start": [x, y]}

    h_lo, h_hi = s.get("heading", [0, 360])
    c["heading"] = round(rng.uniform(h_lo, h_hi)) % 360
    if s.get("motion", base.get("motion")) == "drift":
        c["heading"] = round(catalog.get("current", {}).get("heading", c["heading"]))
    if "speed" in s:
        c["speed_mps"] = round(rng.uniform(*s["speed"]), 2)
    c["size_m"] = round(base["size_m"] * rng.uniform(*s.get("size", [0.85, 1.15])), 2)
    if "motion" in s:
        c["motion"] = s["motion"]
    if "hail" in s:
        options = s["hail"]
        c["hail"] = rng.choices(list(options), list(options.values()))[0]
    for key in ("transponder", "signature"):
        if key in s:
            c[key] = s[key]
    if "spawn_t" in s:
        c["spawn_t"] = round(rng.uniform(*s["spawn_t"]), 1)
    if "label" in s:
        conf = rng.uniform(*s.get("conf", [0.5, 0.6]))
        step = rng.uniform(*s.get("step", [0, 0]))
        cap = s.get("conf_max", 0.97)
        c["label_track"] = [{"look": i, "label": s["label"], "conf": round(min(cap, conf + i * step), 2)}
                            for i in range(int(s.get("looks", 3)))]
    if s.get("survey"):
        c["motion"] = "waypoints"
        c["waypoints"] = [list(_point(area, rng, harbor, radius)) for _ in range(rng.randint(2, 4))]
        c["loop"] = True
    answers = s.get("answers")
    if answers and rng.random() < answers["p"]:
        c["events"] = [{"t": round(rng.uniform(*answers["t"])),
                        "set": {"hail": "intermittent", "transponder": answers["transponder"]}}]
    return c


def _reachable_variants(slot: dict[str, Any], regions: dict[str, Any],
                        harbor: dict[str, Any], radius: int) -> Iterator[dict[str, Any]]:
    variants = slot.get("variants", [{}])
    center = harbor["sensor_center"]
    for variant in variants:
        region = variant.get("region", slot.get("region"))
        for x0, y0, width, height in regions[region]:
            for x in range(x0, x0 + width + 1, 20):
                for y in range(y0, y0 + height + 1, 20):
                    if is_water(harbor, (x, y)) and math.dist((x, y), (center["x"], center["y"])) <= radius:
                        break
                else:
                    continue
                break
            else:
                continue
            break
        else:
            continue
        yield variant


def water_area_km2(harbor: dict[str, Any], radius: int) -> float:
    bounds = harbor["bounds"]
    center = harbor["sensor_center"]
    step = 50
    covered = 0
    for x in range(step // 2, int(bounds["w"]), step):
        for y in range(step // 2, int(bounds["h"]), step):
            if math.dist((x, y), (center["x"], center["y"])) <= radius and is_water(harbor, (x, y)):
                covered += 1
    return round(covered * step * step / 1_000_000, 2)


def _point(area: list[list[float]], rng: random.Random, harbor: dict[str, Any], radius: int) -> tuple[int, int]:
    center = harbor["sensor_center"]
    for _ in range(150):
        x0, y0, w, h = rng.choice(area)
        p = (round(x0 + rng.uniform(0, w)), round(y0 + rng.uniform(0, h)))
        if is_water(harbor, p) and math.dist(p, (center["x"], center["y"])) <= radius:
            return p
    candidates = [(x, y) for x0, y0, w, h in area
                  for x in range(x0, x0 + w + 1, 10)
                  for y in range(y0, y0 + h + 1, 10)
                  if is_water(harbor, (x, y)) and math.dist((x, y), (center["x"], center["y"])) <= radius]
    if candidates:
        return rng.choice(candidates)
    raise ValueError(f"no water inside the {radius} m watch radius for this contact region")

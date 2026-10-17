from __future__ import annotations

import random
from collections import Counter
from typing import Any

from .simulator import is_water


def randomize(template: dict[str, Any], seed: int, catalog: dict[str, Any], harbor: dict[str, Any]) -> dict[str, Any]:
    spec = template["randomize"]
    cfg = catalog["randomizer"]
    kind = cfg[spec["kind"]]
    slots, regions = cfg["slots"], cfg["regions"]
    rng = random.Random(f"randomize:{spec['kind']}:{seed}")
    lo, hi = spec.get("count", [8, 15])
    count = rng.randint(lo, hi)

    picks = [rng.choice(group) for group in kind["required"]]
    used = Counter(picks)
    while len(picks) < count:
        open_ = {n: w for n, w in kind["fill"].items() if used[n] < slots[n].get("max", count)}
        if not open_:
            break
        name = rng.choices(list(open_), list(open_.values()))[0]
        picks.append(name)
        used[name] += 1
    rng.shuffle(picks)

    prefix = spec.get("prefix", "R")
    contacts = [_contact(f"{prefix}-{i + 1:02d}", slots[name], regions, rng, harbor, catalog)
                for i, name in enumerate(picks)]
    out = {k: v for k, v in template.items() if k != "randomize"}
    out.update(seed=seed, contacts=contacts,
               description=f"Seed {seed}: {len(contacts)} contacts. {template.get('description', '')}".strip())
    if spec.get("clock_starts"):
        out["clock_start"] = rng.choice(spec["clock_starts"])
    return out


def _contact(cid: str, slot: dict[str, Any], regions: dict[str, Any], rng: random.Random,
             harbor: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    s = {k: v for k, v in slot.items() if k != "variants"}
    if slot.get("variants"):
        s.update(rng.choice(slot["variants"]))
    archetype = s["archetype"]
    base = catalog["archetypes"][archetype]
    area = regions[s["region"]]
    x, y = _point(area, rng, harbor)
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
        c["waypoints"] = [list(_point(area, rng, harbor)) for _ in range(rng.randint(2, 4))]
        c["loop"] = True
    answers = s.get("answers")
    if answers and rng.random() < answers["p"]:
        c["events"] = [{"t": round(rng.uniform(*answers["t"])),
                        "set": {"hail": "intermittent", "transponder": answers["transponder"]}}]
    return c


def _point(area: list[list[float]], rng: random.Random, harbor: dict[str, Any]) -> tuple[int, int]:
    for _ in range(200):
        x0, y0, w, h = rng.choice(area)
        p = (round(x0 + rng.uniform(0, w)), round(y0 + rng.uniform(0, h)))
        if is_water(harbor, p):
            return p
    x0, y0, w, h = area[0]
    return round(x0 + w / 2), round(y0 + h / 2)

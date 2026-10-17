from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from .classifier import Classifier, Observation, build_classifier
from .engine import Decision, Memory, decide
from .facts import clock_at, derive_facts
from .rules import Rules
from .simulator import SimContact, Simulator


@dataclass
class World:
    harbor: dict[str, Any]
    catalog: dict[str, Any]
    presets: list[dict[str, Any]]

    @classmethod
    def load(cls, config_dir: Path) -> World:
        y = YAML(typ="safe")
        return cls(
            harbor=y.load((config_dir / "harbor.yaml").read_text()),
            catalog=y.load((config_dir / "scenarios.yaml").read_text()),
            presets=y.load((config_dir / "twist_presets.yaml").read_text()) or [],
        )

    def scenario(self, name: str) -> dict[str, Any]:
        try:
            return self.catalog["scenarios"][name]
        except KeyError:
            raise KeyError(f"unknown scenario '{name}'") from None

    def scenario_list(self) -> list[dict[str, Any]]:
        return [{"id": k, "title": v.get("title", k), "description": v.get("description", ""),
                 "mode": v.get("mode", "security"), "duration_s": v.get("duration_s", 300),
                 "contacts": len(v.get("contacts", [])) + int(v.get("generator", {}).get("count", 0))}
                for k, v in self.catalog["scenarios"].items()]


class Session:
    def __init__(self, rules: Rules, world: World, scenario: str, mode: str = "security",
                 seed: int | None = None, classifier: Classifier | None = None):
        self.rules = rules
        self.world = world
        self.scenario_name = scenario
        self.scenario = world.scenario(scenario)
        self.mode = mode
        self.sim = Simulator(self.scenario, world.catalog, world.harbor, seed)
        self.seed = self.sim.seed
        self.classifier = classifier or build_classifier(
            rules.classifier.backend, rules.classifier.model_path, world.catalog.get("mock_classifier", {}))
        self.memory: dict[str, Memory] = {}
        self.current: dict[str, Decision] = {}
        self.peak: dict[str, Decision] = {}
        self.first_human_t: dict[str, float] = {}
        self.seen: list[str] = []
        self.departed: set[str] = set()

    @property
    def t(self) -> float:
        return self.sim.t

    @property
    def clock(self) -> str:
        return clock_at(self.scenario.get("clock_start", self.rules.harbor.clock_start), self.sim.t)

    @property
    def duration_s(self) -> float:
        return float(self.scenario.get("duration_s", 300))

    def set_rules(self, rules: Rules) -> None:
        self.rules = rules

    def evaluate(self, c: SimContact) -> Decision:
        rules = self.rules
        mem = self.memory.setdefault(c.id, Memory())
        t = self.sim.t
        obs = Observation(
            contact_id=c.id, t=t, age_s=t - c.spawn_t, look=mem.second_looks, size_m=c.size_m,
            speed_mps=c.speed, signature=c.signature, truth=c.truth, label_track=c.label_track)
        facts = derive_facts(
            contact_id=c.id, t=t, clock=self.clock, position=(c.x, c.y), heading=c.heading,
            speed_mps=c.speed, size_m=c.size_m, signature=c.signature, transponder=c.transponder,
            classification=self.classifier.classify(obs), hail=c.hail_status(t, rules.hail.timeout_s),
            hailed_t=c.hailed_t, hostile=c.hostile, scripted_evasive=c.evasive_flag, trail=c.trail,
            rules=rules)
        d = decide(facts, mem, rules, self.mode)
        if mem.hailed_t is not None and c.hailed_t is None:
            c.hailed_t = mem.hailed_t
        return d

    def step(self, dt: float) -> list[Decision]:
        self.sim.step(dt)
        changed = []
        for c in self.sim.active.values():
            if c.id not in self.memory:
                self.seen.append(c.id)
            d = self.evaluate(c)
            prev = self.current.get(c.id)
            self.current[c.id] = d
            if prev is None or prev.key() != d.key():
                changed.append(d)
            peak = self.peak.get(c.id)
            if peak is None or d.severity() > peak.severity():
                self.peak[c.id] = d
            if d.requires_human and c.id not in self.first_human_t:
                self.first_human_t[c.id] = self.sim.t
        for cid in self.sim.departed:
            self.current.pop(cid, None)
            self.departed.add(cid)
        self.sim.departed.clear()
        return changed

    def run(self, duration_s: float | None = None, dt: float = 1.0) -> None:
        end = self.duration_s if duration_s is None else duration_s
        while self.sim.t < end:
            self.step(dt)

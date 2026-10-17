from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ruamel.yaml import YAML

RUNGS: tuple[str, ...] = ("R0", "R1", "R2", "R3", "R4", "R5")
HUMAN_FLOOR = "R4"
Rung = Literal["R0", "R1", "R2", "R3", "R4", "R5"]
Category = Literal["non_vehicle", "research", "commercial", "military", "improvised", "unknown"]


def rung_index(rung: str) -> int:
    return RUNGS.index(rung)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Shape(Strict):
    type: Literal["rect", "circle", "line"]
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    r: float | None = None
    points: list[tuple[float, float]] | None = None
    width: float = 0

    @model_validator(mode="after")
    def check_fields(self) -> Shape:
        need = {"rect": ("x", "y", "w", "h"), "circle": ("x", "y", "r"), "line": ("points",)}[self.type]
        missing = [f for f in need if getattr(self, f) is None]
        if missing:
            raise ValueError(f"{self.type} shape needs {', '.join(missing)}")
        if self.type == "line" and len(self.points or []) < 2:
            raise ValueError("line shape needs at least two points")
        return self


class Harbor(Strict):
    name: str
    origin: dict[str, float]
    clock_start: str


class ClassifierCfg(Strict):
    backend: str = "mock"
    model_path: str | None = None


class Thresholds(Strict):
    classify_confidence: float = Field(ge=0, le=1)
    non_vehicle_confidence: float = Field(ge=0, le=1)
    improvised_confidence: float = Field(ge=0, le=1)


class Band(Strict):
    high_m: float = Field(ge=0)
    medium_m: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> Band:
        if self.high_m > self.medium_m:
            raise ValueError("high_m must be <= medium_m")
        return self


class CpaCfg(Strict):
    horizon_s: float = Field(default=120, ge=0)
    step_s: float = Field(default=5, gt=0)
    raise_to: Literal["low", "medium", "high"] = "medium"


class ConsequenceCfg(Strict):
    default: Band
    by_kind: dict[str, Band] = {}
    cpa: CpaCfg = CpaCfg()


class TrendCfg(Strict):
    window_s: float = Field(default=30, gt=0)
    closing_mps: float = Field(default=0.05, ge=0)
    loiter_turn_deg: float = Field(default=75, gt=0)
    loiter_speed_mps: float = Field(default=0.03, ge=0)


class Approach(Strict):
    radius_m: float = Field(ge=0)
    cone_deg: float = Field(ge=0, le=180)
    min_speed_mps: float = Field(ge=0)


class Evasion(Strict):
    window_s: float = Field(gt=0)
    turn_deg: float = Field(gt=0)
    speed_jump: float = Field(gt=1)


class HailCfg(Strict):
    timeout_s: float = Field(gt=0)


class Consistency(Strict):
    size_tolerance_m: float = Field(ge=0)
    speed_margin: float = Field(ge=1)


class ClassProfile(Strict):
    max_speed_mps: float = Field(gt=0)


class Loop(Strict):
    max_second_looks: int = Field(ge=0, le=10)
    interval_s: float = Field(gt=0)
    escalate_by: int = Field(ge=1, le=5)


class Ladder(Strict):
    non_vehicle: list[Rung]
    identity_ok_noncritical: list[Rung]
    identity_ok_critical: list[Rung]
    threat: list[Rung]
    evasive: list[Rung]
    military: list[Rung]
    unknown_low: list[Rung]
    unknown_medium_quiet: list[Rung]
    unknown_medium_traffic: list[Rung]
    unknown_high: list[Rung]
    awaiting_hail: list[Rung]

    @model_validator(mode="after")
    def non_empty(self) -> Ladder:
        for name, value in self:
            if not value:
                raise ValueError(f"ladder.{name} needs at least one rung")
        return self


class Windows(Strict):
    urgent: float = Field(gt=0)
    hold_handoff: float = Field(gt=0)
    default: float = Field(gt=0)


class AlertBudget(Strict):
    capacity: float = Field(gt=0)
    weights: dict[Rung, float]
    keep_watching_snooze_s: float = Field(gt=0)


class HandoffCfg(Strict):
    hold_s: float = Field(default=1800, gt=0)
    undo_s: float = Field(default=10, ge=0)
    mock_hold_delay_s: float = Field(default=1.0, ge=0)
    area_radius_m: float = Field(default=400, gt=0)


class Zone(Strict):
    id: str
    name: str
    critical: bool = False
    shape: Shape


class Asset(Strict):
    id: str
    name: str
    kind: str
    operation: str
    description: str | None = None
    active: bool = True
    shape: Shape


class Vessel(Strict):
    id: str
    name: str
    x: float
    y: float


HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Window(Strict):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def hhmm(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError(f"time '{v}' must be HH:MM")
        return v


class RegistryEntry(Strict):
    id: str
    operator: str
    vehicle_type: str
    size_m: float
    signature: str
    authorized_zones: list[str]
    schedule: list[Window]


class RecoveryLadder(Strict):
    possible: list[Rung]
    possible_exhausted: list[Rung]
    confirmed: list[Rung]
    confirmed_traffic: list[Rung]
    confirmed_hazard: list[Rung]


class Recovery(Strict):
    lost_vehicle_id: str
    confirm_confidence: float = Field(ge=0, le=1)
    drift_horizon_s: float = Field(gt=0)
    window_s: float = Field(gt=0)
    ladder: RecoveryLadder


class AdvisorWeights(Strict):
    low_confidence: float = Field(default=0.3, ge=0)
    silent: float = Field(default=0.2, ge=0)
    closing: float = Field(default=0.3, ge=0)
    loitering: float = Field(default=0.15, ge=0)
    anomaly: float = Field(default=0.4, ge=0)
    inconsistent: float = Field(default=0.3, ge=0)
    medium_consequence: float = Field(default=0.1, ge=0)


class AdvisorAnomaly(Strict):
    non_vehicle_max_size_m: float = Field(default=2.5, gt=0)
    non_vehicle_max_speed_mps: float = Field(default=1.5, gt=0)


class LLMCfg(Strict):
    provider: Literal["anthropic"] = "anthropic"
    model: str = "claude-haiku-5-5"
    endpoint: str = "https://api.anthropic.com/v1/messages"
    api_key_env: str = "ANTHROPIC_API_KEY"
    timeout_s: float = Field(default=2.5, gt=0, le=30)
    max_tokens: int = Field(default=200, gt=0, le=2000)


class AdvisorCfg(Strict):
    enabled: bool = True
    backend: Literal["rule", "llm"] = "rule"
    max_raise: int = Field(default=1, ge=0, le=5)
    raise_at: float = Field(default=0.6, ge=0, le=1)
    second_look_at: float = Field(default=0.35, ge=0, le=1)
    timeout_s: float = Field(default=3.0, gt=0, le=30)
    weights: AdvisorWeights = AdvisorWeights()
    anomaly: AdvisorAnomaly = AdvisorAnomaly()
    llm: LLMCfg = LLMCfg()


class NoticeText(Strict):
    to: str = "TO"
    sender: str = "FROM"
    subject_unknown: str = "Unidentified underwater vehicle"
    subject_found: str = "located"
    contact: str = "contact"
    why: str = "Why"
    ruled_out: str = "Ruled out"
    nothing_yet: str = "nothing yet"
    steps: str = "Steps taken"
    none: str = "none"
    recommended: str = "Recommended"
    closing: str = "No physical action has been taken. The next step is yours."


class Jurisdiction(Strict):
    name: str
    registry_source: str
    notice_recipient: str
    hail_channel: str
    language: str
    windows_s: Windows | None = None
    registry: list[RegistryEntry] | None = None
    notice: NoticeText = NoticeText()


class RungText(Strict):
    name: str
    action: str


class ModeCfg(Strict):
    title: str
    customer: str
    handoff_target: str
    rungs: dict[Rung, RungText]

    @model_validator(mode="after")
    def all_rungs(self) -> ModeCfg:
        missing = [r for r in RUNGS if r not in self.rungs]
        if missing:
            raise ValueError(f"mode is missing rung text for {', '.join(missing)}")
        return self


class Rules(Strict):
    harbor: Harbor
    classifier: ClassifierCfg
    thresholds: Thresholds
    classes: dict[str, Category]
    consequence: ConsequenceCfg
    approach: Approach
    evasion: Evasion
    hail: HailCfg
    traffic_radius_m: float = Field(ge=0)
    trend: TrendCfg = TrendCfg()
    consistency: Consistency
    class_profiles: dict[str, ClassProfile]
    loop: Loop
    ladder: Ladder
    human_required_from: Rung
    windows_s: Windows
    alert_budget: AlertBudget
    handoff: HandoffCfg = HandoffCfg()
    zones: list[Zone]
    assets: list[Asset]
    traffic: list[Vessel]
    registry: list[RegistryEntry]
    recovery: Recovery
    modes: dict[Literal["security", "recovery"], ModeCfg]
    advisor: AdvisorCfg = AdvisorCfg()
    jurisdiction: str | None = None
    jurisdictions: dict[str, Jurisdiction] = {}

    @model_validator(mode="after")
    def cross_checks(self) -> Rules:
        if rung_index(self.human_required_from) > rung_index(HUMAN_FLOOR):
            raise ValueError("human_required_from cannot be above R4: Hold and Hand off always need a person")
        if "unknown" not in self.classes:
            raise ValueError("classes must map 'unknown'")
        zone_ids = {z.id for z in self.zones}
        for label, ids in (("zones", [z.id for z in self.zones]), ("assets", [a.id for a in self.assets]),
                           ("registry", [r.id for r in self.registry])):
            dupes = {i for i in ids if ids.count(i) > 1}
            if dupes:
                raise ValueError(f"duplicate {label} ids: {', '.join(sorted(dupes))}")
        if self.jurisdiction is not None and self.jurisdiction not in self.jurisdictions:
            raise ValueError(f"jurisdiction '{self.jurisdiction}' is not defined in jurisdictions")
        registries = [("registry", self.registry)] + [
            (f"jurisdictions.{k}.registry", j.registry) for k, j in self.jurisdictions.items() if j.registry]
        for where, entries in registries:
            ids = [r.id for r in entries]
            dupes = {i for i in ids if ids.count(i) > 1}
            if dupes:
                raise ValueError(f"duplicate {where} ids: {', '.join(sorted(dupes))}")
            for entry in entries:
                unknown = [z for z in entry.authorized_zones if z not in zone_ids]
                if unknown:
                    raise ValueError(f"{where} {entry.id} authorizes unknown zone(s): {', '.join(unknown)}")
        if self.recovery.lost_vehicle_id not in {r.id for r in self.registry}:
            raise ValueError("recovery.lost_vehicle_id must be in the registry")
        for mode in ("security", "recovery"):
            if mode not in self.modes:
                raise ValueError(f"modes.{mode} is required")
        return self

    def band_for(self, kind: str) -> Band:
        return self.consequence.by_kind.get(kind, self.consequence.default)

    @property
    def profile(self) -> Jurisdiction | None:
        return self.jurisdictions.get(self.jurisdiction) if self.jurisdiction else None

    @property
    def active_registry(self) -> list[RegistryEntry]:
        p = self.profile
        return p.registry if p and p.registry is not None else self.registry

    @property
    def registry_source(self) -> str:
        return self.profile.registry_source if self.profile else "the registry"

    @property
    def windows(self) -> Windows:
        p = self.profile
        return p.windows_s if p and p.windows_s else self.windows_s

    @property
    def hail_channel(self) -> str:
        return self.profile.hail_channel if self.profile else "acoustic modem and VHF 16"

    @property
    def notice(self) -> NoticeText:
        return self.profile.notice if self.profile else NoticeText()

    @property
    def language(self) -> str:
        return self.profile.language if self.profile else "en"

    def handoff_target(self, mode: str) -> str:
        if mode == "security" and self.profile:
            return self.profile.notice_recipient
        return self.modes[mode].handoff_target

    def config_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]

    def registry_entry(self, vehicle_id: str | None) -> RegistryEntry | None:
        if not vehicle_id:
            return None
        return next((r for r in self.active_registry if r.id == vehicle_id), None)

    def requires_human(self, rung: str) -> bool:
        return rung_index(rung) >= rung_index(self.human_required_from)


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 120
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def load_yaml_text(text: str) -> Any:
    return YAML(typ="safe").load(text)


def plain(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))


def parse_rules(data: Any) -> Rules:
    return Rules.model_validate(data)


SEGMENT = re.compile(r"([^.\[\]]+)|\[([^\]]+)\]")


def _segments(path: str) -> list[tuple[str, str]]:
    out = []
    for key, sel in SEGMENT.findall(path):
        out.append(("key", key) if key else ("sel", sel))
    if not out:
        raise ValueError(f"empty path '{path}'")
    return out


def _step(node: Any, seg: tuple[str, str], path: str) -> Any:
    kind, val = seg
    if kind == "key":
        if not isinstance(node, dict) or val not in node:
            raise KeyError(f"'{val}' not found in path '{path}'")
        return node[val]
    if not isinstance(node, list):
        raise KeyError(f"[{val}] applied to a non-list in path '{path}'")
    if val.isdigit():
        return node[int(val)]
    for item in node:
        if isinstance(item, dict) and str(item.get("id")) == val:
            return item
    raise KeyError(f"no item with id '{val}' in path '{path}'")


def apply_ops(data: Any, ops: list[dict[str, Any]]) -> Any:
    out = copy.deepcopy(data)
    for op in ops:
        path = op["path"]
        action = op.get("op", "set")
        segs = _segments(path)
        parent = out
        for seg in segs[:-1]:
            parent = _step(parent, seg, path)
        kind, val = segs[-1]
        if action == "append":
            target = _step(parent, segs[-1], path)
            if not isinstance(target, list):
                raise ValueError(f"append target '{path}' is not a list")
            target.append(copy.deepcopy(op["value"]))
        elif action == "remove":
            if kind == "key":
                parent.pop(val)
            else:
                parent.remove(_step(parent, segs[-1], path))
        elif action == "set":
            if kind == "key":
                if not isinstance(parent, dict):
                    raise KeyError(f"cannot set '{val}' on a non-mapping in '{path}'")
                parent[val] = copy.deepcopy(op["value"])
            else:
                item = _step(parent, segs[-1], path)
                parent[parent.index(item)] = copy.deepcopy(op["value"])
        else:
            raise ValueError(f"unknown op '{action}'")
    return out


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list) and obj and all(isinstance(i, dict) and "id" in i for i in obj):
        for item in obj:
            out.update(flatten(item, f"{prefix}[{item['id']}]"))
    else:
        out[prefix] = obj
    return out


def field_diff(before: Any, after: Any) -> list[dict[str, Any]]:
    a, b = flatten(plain(before)), flatten(plain(after))
    changes = []
    for key in sorted(set(a) | set(b)):
        if a.get(key, "∅") != b.get(key, "∅"):
            changes.append({"path": key, "before": a.get(key), "after": b.get(key)})
    return changes


def _merge_into(target: Any, new: Any) -> Any:
    if isinstance(target, dict) and isinstance(new, dict):
        for key in list(target.keys()):
            if key not in new:
                del target[key]
        for key, value in new.items():
            if key in target:
                target[key] = _merge_into(target[key], value)
            else:
                target[key] = value
        return target
    if isinstance(target, list) and isinstance(new, list):
        if len(target) == len(new):
            for i, value in enumerate(new):
                target[i] = _merge_into(target[i], value)
            return target
        return new
    return new


class RulesStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.version = 0
        self.error: str | None = None
        self.mtime = 0.0
        self.text = ""
        self.data: dict[str, Any] = {}
        self.rules: Rules
        self._load_initial()

    def _load_initial(self) -> None:
        text = self.path.read_text()
        data = load_yaml_text(text)
        self.rules = parse_rules(data)
        self.data = plain(data)
        self.text = text
        self.mtime = self.path.stat().st_mtime
        self.version = 1

    def validate_text(self, text: str) -> tuple[dict[str, Any], Rules]:
        data = load_yaml_text(text)
        return plain(data), parse_rules(data)

    def check_reload(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        with self.lock:
            try:
                mtime = self.path.stat().st_mtime
            except FileNotFoundError:
                self.error = "rules.yaml is missing"
                return None
            if mtime == self.mtime:
                return None
            self.mtime = mtime
            text = self.path.read_text()
            if text == self.text:
                return None
            try:
                data, rules = self.validate_text(text)
            except Exception as exc:
                self.error = format_error(exc)
                return None
            before = self.data
            self._commit(text, data, rules)
            return before, data

    def _commit(self, text: str, data: dict[str, Any], rules: Rules) -> None:
        self.text = text
        self.data = data
        self.rules = rules
        self.error = None
        self.version += 1

    def write_text(self, text: str) -> tuple[dict[str, Any], dict[str, Any]]:
        with self.lock:
            data, rules = self.validate_text(text)
            before = self.data
            self.path.write_text(text)
            self.mtime = self.path.stat().st_mtime
            self._commit(text, data, rules)
            return before, data

    def write_data(self, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        with self.lock:
            parse_rules(data)
            y = _yaml()
            doc = y.load(self.text)
            _merge_into(doc, plain(data))
            buf = io.StringIO()
            y.dump(doc, buf)
            return self.write_text(buf.getvalue())


def format_error(exc: Exception) -> str:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            parts = []
            for e in errors()[:4]:
                loc = ".".join(str(p) for p in e.get("loc", ()))
                parts.append(f"{loc}: {e.get('msg')}" if loc else str(e.get("msg")))
            return "; ".join(parts)
        except Exception:
            pass
    return str(exc).splitlines()[0][:300] if str(exc) else exc.__class__.__name__

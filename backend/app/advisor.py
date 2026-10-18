from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .engine import Decision, Memory, advise_decision
from .facts import Facts
from .rules import AdvisorCfg, LLMCfg, Rules, rung_index

log = logging.getLogger("quietwater.advisor")

AMBIGUOUS_OUTCOMES = frozenset({
    "unknown_low", "unknown_low_escalated", "unknown_medium_quiet", "unknown_medium_traffic", "awaiting_hail",
    "rec_possible", "rec_possible_exhausted",
})
HARD_OUTCOMES = frozenset({"threat", "evasive", "military", "unknown_high"})
FAIL_SAFE_REASON = "Advisor unavailable; escalated one rung to fail safe."
SYSTEM_PROMPT = (
    "You review one underwater sonar contact that a rules engine marked ambiguous. You may only suggest "
    "raising its response by whole rungs or asking for a second sonar look. You can never lower it. "
    "Reply with one JSON object and nothing else: "
    '{"suggested_tier_raise": <integer 0-2>, "second_look": <true|false>, '
    '"reason": "<one short line>", "confidence": <number 0-1>}'
)


@dataclass(frozen=True)
class AdvisorInput:
    track: str
    outcome: str
    rung: str
    label: str
    scan_label: str
    confidence: float
    classify_threshold: float
    size_m: float
    speed_mps: float
    hail: str
    consequence: str
    trend: str
    cpa_m: float | None
    cpa_in_s: float | None
    cpa_asset: str | None
    cpa_level: str | None
    consistent: bool
    anomaly: str | None
    registered: bool
    zone_critical: bool

    def key(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


@dataclass(frozen=True)
class Advice:
    suggested_tier_raise: int
    second_look: bool
    reason: str
    confidence: float


@dataclass(frozen=True)
class AdvisorRecord:
    source: str
    inputs: dict[str, Any]
    advice: Advice
    applied_raise: int
    clamped: bool
    error: str | None = None

    def receipt(self, applied: bool, raised: int) -> dict[str, Any]:
        return {"source": self.source, "inputs": self.inputs, "suggestion": asdict(self.advice),
                "applied": applied, "raised_rungs": raised, "clamped": self.clamped, "error": self.error,
                "reason": self.advice.reason}

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> AdvisorRecord:
        return cls(**{**d, "advice": Advice(**d["advice"])})


class AdvisorError(Exception):
    pass


class Advisor(Protocol):
    name: str

    def advise(self, x: AdvisorInput) -> Advice: ...


class AdviceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    suggested_tier_raise: int = Field(ge=-5, le=5)
    second_look: bool = False
    reason: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0, le=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def numeric(cls, v: Any) -> Any:
        return float(v) if isinstance(v, int) and not isinstance(v, bool) else v

    @field_validator("reason")
    @classmethod
    def one_line(cls, v: str) -> str:
        if "\n" in v.strip():
            raise ValueError("reason must be one line")
        return v.strip()


def parse_advice(text: str) -> Advice:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise AdvisorError("no JSON object in advisor output")
    try:
        m = AdviceModel.model_validate(json.loads(text[start:end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AdvisorError(f"invalid advisor output: {str(exc).splitlines()[0][:160]}") from exc
    return Advice(m.suggested_tier_raise, m.second_look, m.reason, m.confidence)


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


class RuleBasedAdvisor:
    name = "rule"

    def __init__(self, cfg: AdvisorCfg):
        self.cfg = cfg

    def advise(self, x: AdvisorInput) -> Advice:
        w = self.cfg.weights
        factors: list[tuple[float, str]] = []
        if x.confidence < x.classify_threshold:
            gap = (x.classify_threshold - x.confidence) / max(x.classify_threshold, 1e-6)
            factors.append((w.low_confidence * gap, f"low confidence ({_pct(x.confidence)})"))
        if x.hail in ("none", "mismatch"):
            factors.append((w.silent, "silent to the hail" if x.hail == "none" else "hail answer does not match"))
        if x.trend == "closing" and x.cpa_level in ("medium", "high"):
            target = f" on {x.cpa_asset}" if x.cpa_asset else ""
            factors.append((w.closing, f"closing{target}"))
        if x.trend == "loitering":
            factors.append((w.loitering, "loitering"))
        if x.anomaly:
            factors.append((w.anomaly, x.anomaly))
        if not x.consistent:
            factors.append((w.inconsistent, "size or speed does not fit its class"))
        if x.consequence == "medium":
            factors.append((w.medium_consequence, "inside a medium-consequence band"))
        score = round(min(1.0, sum(f for f, _ in factors)), 3)
        named = [t for _, t in sorted(factors, key=lambda f: -f[0])[:3]]
        why = ", ".join(named) if named else "no compounding signals"
        if score >= self.cfg.raise_at:
            return Advice(1, False, f"Compounding signals: {why}.", score)
        if score >= self.cfg.second_look_at and rung_index(x.rung) < rung_index("R1"):
            return Advice(0, True, f"Worth a second look: {why}.", score)
        return Advice(0, False, f"No raise: {why}.", score)


Transport = Callable[[LLMCfg, str, dict[str, Any]], str]


def anthropic_transport(cfg: LLMCfg, api_key: str, body: dict[str, Any]) -> str:
    req = urllib.request.Request(
        cfg.endpoint, data=json.dumps(body).encode(), method="POST",
        headers={"content-type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300].replace("\n", " ")
        raise AdvisorError(f"HTTP {exc.code}: {detail}") from exc
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    if not parts:
        raise AdvisorError("model returned no text")
    return "".join(parts)


class LLMAdvisor:
    name = "llm"

    def __init__(self, cfg: LLMCfg, transport: Transport | None = None):
        self.cfg = cfg
        self.transport = transport or anthropic_transport

    def advise(self, x: AdvisorInput) -> Advice:
        key = os.environ.get(self.cfg.api_key_env, "")
        if not key and self.transport is anthropic_transport:
            raise AdvisorError(f"${self.cfg.api_key_env} is not set")
        body = {"model": self.cfg.model, "max_tokens": self.cfg.max_tokens, "thinking": {"type": "disabled"},
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": json.dumps(asdict(x), sort_keys=True)}]}
        return parse_advice(self.transport(self.cfg, key, body))


class AdvisorCache:
    def __init__(self, path: Path | None = None, maxsize: int = 20000):
        self.path = path
        self.maxsize = maxsize
        self.lock = threading.Lock()
        self.items: OrderedDict[str, AdvisorRecord] = OrderedDict()
        if path and path.exists():
            try:
                for k, v in json.loads(path.read_text()).items():
                    self.items[k] = AdvisorRecord.from_json(v)
            except Exception:
                log.exception("advisor cache unreadable; starting empty")

    def get(self, key: str) -> AdvisorRecord | None:
        with self.lock:
            return self.items.get(key)

    def put(self, key: str, record: AdvisorRecord) -> None:
        with self.lock:
            self.items[key] = record
            while len(self.items) > self.maxsize:
                self.items.popitem(last=False)
            if self.path and record.source.startswith("llm"):
                persisted = {k: v.to_json() for k, v in self.items.items() if v.source.startswith("llm")}
                self.path.write_text(json.dumps(persisted))


_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="advisor")


class AdvisorLayer:
    def __init__(self, cfg: AdvisorCfg, config_hash: str, cache: AdvisorCache | None = None,
                 primary: Advisor | None = None):
        self.cfg = cfg
        self.config_hash = config_hash
        self.cache = cache or AdvisorCache()
        self.llm_calls = 0
        self.fallback = RuleBasedAdvisor(cfg)
        if primary is not None:
            self.primary: Advisor = primary
        elif cfg.backend == "llm":
            self.primary = LLMAdvisor(cfg.llm)
        else:
            self.primary = self.fallback

    @classmethod
    def from_rules(cls, rules: Rules, cache: AdvisorCache | None = None) -> AdvisorLayer:
        return cls(rules.advisor, rules.config_hash(), cache)

    def _call(self, advisor: Advisor, x: AdvisorInput) -> Advice:
        if advisor is self.fallback:
            return advisor.advise(x)
        future = _POOL.submit(advisor.advise, x)
        try:
            advice = future.result(timeout=self.cfg.timeout_s)
        except FutureTimeout as exc:
            future.cancel()
            raise AdvisorError(f"timed out after {self.cfg.timeout_s:.1f} s") from exc
        if not isinstance(advice, Advice):
            raise AdvisorError("advisor returned no advice")
        return advice

    def consult(self, x: AdvisorInput) -> AdvisorRecord:
        key = f"{self.config_hash}:{self.primary.name}:{x.key()}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        record = self._consult(x)
        self.cache.put(key, record)
        return record

    def _consult(self, x: AdvisorInput) -> AdvisorRecord:
        if self.primary.name == "llm":
            self.llm_calls += 1
        source, error, advice = self.primary.name, None, None
        try:
            advice = self._call(self.primary, x)
        except Exception as exc:
            error = f"{self.primary.name}: {exc}"
            log.warning("advisor %s failed (%s); falling back", self.primary.name, exc)
            if self.primary is not self.fallback:
                try:
                    advice, source = self.fallback.advise(x), "rule_fallback"
                except Exception as exc2:
                    error += f"; rule: {exc2}"
                    log.error("rule-based advisor also failed (%s); failing safe", exc2)
        if advice is None:
            log.error("no advisor available for %s; escalating one rung", x.outcome)
            return AdvisorRecord("fail_safe", asdict(x), Advice(1, False, FAIL_SAFE_REASON, 0.0), 1, False, error)
        raw = advice.suggested_tier_raise
        applied = max(0, min(raw, self.cfg.max_raise))
        return AdvisorRecord(source, asdict(x), advice, applied, applied != raw, error)


def anomaly_of(f: Facts, rules: Rules) -> str | None:
    a = rules.advisor.anomaly
    if f.category != "non_vehicle":
        return None
    if f.size_m > a.non_vehicle_max_size_m:
        return f"{f.size_m:.1f} m is large for {f.label}"
    if f.speed_mps > a.non_vehicle_max_speed_mps:
        return f"{f.speed_mps:.1f} m/s is fast for {f.label}"
    return None


def is_ambiguous(f: Facts, d: Decision, rules: Rules) -> bool:
    if d.outcome in HARD_OUTCOMES or d.urgency == "urgent":
        return False
    if d.outcome in AMBIGUOUS_OUTCOMES:
        return True
    if f.category == "unknown" or f.confidence < rules.thresholds.classify_confidence and f.category != "non_vehicle":
        return d.outcome not in ("identity_ok_noncritical", "identity_ok_critical")
    return anomaly_of(f, rules) is not None


def build_input(f: Facts, d: Decision, rules: Rules) -> AdvisorInput:
    cpa = f.cpa or {}
    return AdvisorInput(
        track=d.track, outcome=d.outcome, rung=d.rung, label=f.label, scan_label=f.scan_label,
        confidence=round(f.confidence, 2), classify_threshold=rules.thresholds.classify_confidence,
        size_m=round(f.size_m, 1), speed_mps=round(f.speed_mps, 1), hail=f.hail, consequence=f.consequence,
        trend=f.trend, cpa_m=round(cpa["distance_m"], -1) if cpa else None,
        cpa_in_s=round(cpa["in_s"], -1) if cpa else None,
        cpa_asset=(cpa.get("asset") or {}).get("name") if cpa else None, cpa_level=cpa.get("level") if cpa else None,
        consistent=f.consistent, anomaly=anomaly_of(f, rules), registered=f.registered,
        zone_critical=f.zone_critical,
    )


def review(f: Facts, mem: Memory, rules: Rules, mode: str, d: Decision, layer: AdvisorLayer) -> Decision:
    if not rules.advisor.enabled or not is_ambiguous(f, d, rules):
        return d
    record = layer.consult(build_input(f, d, rules))
    second = record.advice.second_look
    if record.applied_raise == 0 and not (second and rung_index(d.rung) < rung_index("R1")):
        return replace(d, ambiguous=True, advisor=record.receipt(False, 0))
    new = advise_decision(f, mem, rules, mode, d, record.applied_raise, second, record.advice.reason)
    if new.severity() < d.severity() or rung_index(new.rung) < rung_index(d.rung):
        return replace(d, ambiguous=True, advisor=record.receipt(False, 0))
    raised = rung_index(new.rung) - rung_index(d.rung)
    return replace(new, ambiguous=True, ai_raised_tier=raised, ai_reason=record.advice.reason if raised else None,
                   advisor=record.receipt(raised > 0, raised))

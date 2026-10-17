from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Observation:
    contact_id: str
    t: float
    age_s: float
    look: int
    size_m: float
    speed_mps: float
    signature: str
    truth: str | None = None
    label_track: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Classification:
    label: str
    confidence: float
    scores: dict[str, float] = field(default_factory=dict)
    source: str = "mock"


class Classifier(Protocol):
    name: str

    def classify(self, obs: Observation) -> Classification: ...


class MockClassifier:
    """Scripted sensor stand-in. Uses a contact's label_track when present,
    otherwise derives a label from ground truth with seeded noise. Each second
    look adds confidence, the way a closer sonar pass would."""

    name = "mock"

    def __init__(self, profile: dict[str, Any]):
        self.base: dict[str, float] = profile.get("base", {})
        self.per_look = float(profile.get("per_look", 0.06))
        self.noise = float(profile.get("noise", 0.03))

    def classify(self, obs: Observation) -> Classification:
        scripted = self._scripted(obs)
        if scripted:
            return scripted
        truth = obs.truth or "unknown"
        rng = random.Random(f"{obs.contact_id}:{obs.look}")
        conf = self.base.get(truth, 0.5) + obs.look * self.per_look + rng.uniform(-self.noise, self.noise)
        conf = round(max(0.05, min(0.99, conf)), 2)
        label = truth if conf >= 0.5 else "unknown"
        return Classification(label, conf, {label: conf}, "mock")

    @staticmethod
    def _scripted(obs: Observation) -> Classification | None:
        by_look = [e for e in obs.label_track if "look" in e and e["look"] <= obs.look]
        by_time = [e for e in obs.label_track if "t" in e and e["t"] <= obs.age_s]
        entry = None
        if by_look:
            entry = max(by_look, key=lambda e: e["look"])
        elif by_time:
            entry = max(by_time, key=lambda e: e["t"])
        if not entry:
            return None
        conf = float(entry["conf"])
        return Classification(entry["label"], conf, {entry["label"]: conf}, "script")


class PretrainedClassifier:
    """Adapter for a real sonar classifier.

    Wire a pretrained model here. `classify` receives the same Observation the
    mock gets; return a Classification whose label is a key of `classes` in
    rules.yaml (map model labels with `label_map`). Select it with
    `classifier.backend: pretrained` and `classifier.model_path` in rules.yaml.
    """

    name = "pretrained"

    def __init__(self, model_path: str | None, label_map: dict[str, str] | None = None):
        self.model_path = model_path
        self.label_map = label_map or {}
        self.model = self._load(model_path)

    def _load(self, model_path: str | None) -> Any:
        raise NotImplementedError("Load your model (ONNX/TorchScript) from classifier.model_path here")

    def features(self, obs: Observation) -> list[float]:
        return [obs.size_m, obs.speed_mps, float(obs.look)]

    def classify(self, obs: Observation) -> Classification:
        raise NotImplementedError("Run self.model on self.features(obs) and map the top label")


def build_classifier(backend: str, model_path: str | None, mock_profile: dict[str, Any]) -> Classifier:
    if backend == "mock":
        return MockClassifier(mock_profile)
    if backend == "pretrained":
        return PretrainedClassifier(model_path)
    raise ValueError(f"unknown classifier backend '{backend}'")

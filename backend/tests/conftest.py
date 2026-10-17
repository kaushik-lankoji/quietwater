from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.classifier import Classification
from app.facts import AssetRef, Facts
from app.rules import RulesStore

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def rules():
    return RulesStore(REPO / "config" / "rules.yaml").rules


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    shutil.copytree(REPO / "config", tmp_path / "config")
    (tmp_path / "data").mkdir()
    return tmp_path


def asset(distance: float = 900, kind: str = "ship") -> AssetRef:
    return AssetRef("mt-sea-venture", "MT Sea Venture", kind, "bunkering", distance)


def make_facts(rules, **kw) -> Facts:
    base = dict(
        contact_id="T-1", t=0.0, clock="09:00:00", position=(1000.0, 1000.0), heading=90.0, speed_mps=0.3,
        size_m=1.4, signature="unclassified", transponder=None, label="unknown", confidence=0.45,
        category="unknown", hail="none", hail_age_s=20.0, consequence="low", nearest_asset=asset(),
    )
    base.update(kw)
    if "label" in kw and "category" not in kw:
        base["category"] = rules.classes.get(kw["label"], "unknown")
    return Facts(**base)


def classification(label: str, conf: float) -> Classification:
    return Classification(label, conf)

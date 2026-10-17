from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.advisor import AdvisorCache, AdvisorInput, AdvisorLayer, LLMAdvisor  # noqa: E402
from app.rules import RulesStore  # noqa: E402

BASE = AdvisorInput(
    track="security", outcome="unknown_medium_quiet", rung="R2", label="unknown", scan_label="unknown",
    confidence=0.38, classify_threshold=0.7, size_m=1.4, speed_mps=0.3, hail="none", consequence="medium",
    trend="closing", cpa_m=150, cpa_in_s=60, cpa_asset="MT Sea Venture", cpa_level="medium", consistent=True,
    anomaly=None, registered=False, zone_critical=False,
)
CASES = {
    "closing, silent, low confidence": BASE,
    "quiet and far": replace(BASE, trend="steady", consequence="low", cpa_m=None, cpa_in_s=None, cpa_asset=None,
                             cpa_level=None, outcome="unknown_low", rung="R1", confidence=0.6),
    "3 m 'fish'": replace(BASE, label="biologic", scan_label="marine_life", confidence=0.9, size_m=3.4,
                          anomaly="3.4 m is large for biologic", outcome="non_vehicle", rung="R0"),
}


def main() -> int:
    env = os.environ.get("ANTHROPIC_API_KEY", "")
    print(f"ANTHROPIC_API_KEY set: {bool(env)} (length {len(env)})")
    if not env:
        print("Set it in this terminal first: export ANTHROPIC_API_KEY=...")
        return 1
    rules = RulesStore(Path(__file__).resolve().parents[2] / "config" / "rules.yaml").rules
    cfg = rules.advisor.llm
    print(f"model {cfg.model}, timeout {cfg.timeout_s}s\n")
    advisor = LLMAdvisor(cfg)
    ok = True
    for name, x in CASES.items():
        t0 = time.time()
        try:
            a = advisor.advise(x)
            print(f"[{time.time() - t0:.2f}s] {name}\n    raise={a.suggested_tier_raise} second_look={a.second_look} "
                  f"confidence={a.confidence}\n    reason: {a.reason}")
        except Exception as exc:
            ok = False
            print(f"[{time.time() - t0:.2f}s] {name}\n    FAILED: {exc}")
    layer = AdvisorLayer(rules.advisor.model_copy(update={"backend": "llm"}), "smoke", AdvisorCache())
    t0 = time.time()
    record = layer.consult(BASE)
    again = time.time()
    layer.consult(BASE)
    print(f"\nthrough the guarded layer: source={record.source} applied_raise={record.applied_raise} "
          f"clamped={record.clamped} error={record.error} ({again - t0:.2f}s)")
    print(f"second identical call served from cache in {time.time() - again:.4f}s")
    return 0 if ok and record.source == "llm" else 1


if __name__ == "__main__":
    raise SystemExit(main())

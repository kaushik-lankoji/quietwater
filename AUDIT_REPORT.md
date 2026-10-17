# Pipeline audit report

Branch `pipeline-audit`, tagged `v3-audited`. Roll back with tag `pre-audit`. The full trace is in `PIPELINE_AUDIT.md`.

## 1. FIXED

- Added the AI layer, which did not exist: `backend/app/advisor.py` with an `Advisor` protocol, `RuleBasedAdvisor` (default, offline, deterministic) and `LLMAdvisor` (config flag, off by default, key read from env).
- The advisor runs only on contacts the engine marks ambiguous (`is_ambiguous`). Hard triggers (improvised, hostile, closing fast, evasive, military, high consequence) are never sent to it.
- Guardrails are enforced in code. Output is strictly validated and clamped to 0..`max_raise`, so it can never lower a rung.
- Advisor failures are handled in code. Errors, timeouts, malformed JSON and a missing API key fall back to the rule-based advisor. If both fail, the contact goes up one rung.
- Advisor answers are cached per (contact snapshot, config hash), in memory and on disk for LLM answers, so replays and Twist diffs stay deterministic.
- Every advisor call goes into the decision receipt and audit log (inputs, suggestion, applied or clamped, source, error). `ambiguous`, `ai_raised_tier` and `ai_reason` are on every decision, so they appear in receipts and hand-off data.
- Fixed a gap found by the new tests: an advisor step up from R0 now goes through the counted look-again loop (max 2, then up one rung) instead of holding at R1 forever, and a raise plus a second look no longer stack.
- Consequence now uses the closest point of approach, a straight-line projection over `consequence.cpa.horizon_s` that raises consequence up to `cpa.raise_to`. Every decision also has a closing / leaving / loitering / steady trend.
- Added the coarse fast-scan label (`debris`, `marine_life`, `known_vehicle`, `unknown`) to facts and decisions, keeping the fine labels the hard triggers need.
- Added jurisdiction profiles (LA, Singapore, EU) in `rules.yaml`. Each sets the registry source and registry, notice recipient, hail channel, notice language and response windows, all switchable by config.
- Notice drafts use the active jurisdiction's recipient and language; the EU profile drafts in Dutch.
- R1 is renamed "Look again", as in the target.
- The R2 hail text reads the jurisdiction's channel.
- Receipts and audit entries carry a `config_hash` (content hash of the rules), not just a version counter.
- The Alert Budget gains `total` and `needed_operator`, so `quiet + needed_operator == total` always holds.
- `/api/health` reports the config hash, the jurisdiction, and the advisor state.
- Wrote `PIPELINE_AUDIT.md` (as-found and after diagrams, 10 deviations with status) and updated the README, demo script and `BACKEND_NOTES.md`.

## 2. VERIFIED WORKING

`make test`: **123 passed** (44 new), ruff clean, TypeScript type check clean. `make build` succeeds.

| Requirement | Tests |
| --- | --- |
| Every branch of the decision tree reaches the correct rung | `test_engine.py` (every S0–S5 and recovery M1–M3 branch), `test_cpa_raises_low_consequence_to_the_configured_cap`, `test_trend_detects_closing_leaving_loitering_and_new`, `test_scan_label_vocabulary` |
| Look-again cap of 2, then one rung; no infinite loops | `test_loop_cap_escalates_one_rung_and_never_loops_forever`, `test_loop_cap_zero_escalates_immediately`, `test_anomalous_non_vehicle_gets_a_capped_second_look` |
| AI never lowers a tier (property test) and never overrides a hard trigger | `test_advisor_never_lowers_a_decision_property` (600 random cases), `test_hard_triggers_are_never_sent_to_the_advisor_or_changed` (6 triggers), `test_negative_and_oversized_suggestions_are_clamped`, `test_recovery_track_can_be_raised_but_never_lowered` |
| Advisor failure, timeout and malformed output fall back safely | `test_advisor_failures_fall_back_to_rule_based` (error, timeout, prose, bad JSON types), `test_missing_api_key_falls_back_without_network`, `test_when_every_advisor_fails_the_contact_goes_up_one_rung`, `test_valid_llm_json_is_parsed_strictly` |
| Advisor determinism and caching | `test_llm_answers_are_cached_per_snapshot_and_config`, `test_llm_cache_persists_to_disk`, `test_replay_is_deterministic_even_with_a_noisy_model` (3 scenarios) |
| R4/R5 cannot run without operator approval, via the API | `test_r4_r5_are_never_automated_and_need_operator_approval`, `test_handoff_approve_then_send_draft` |
| Never emits an external alert on its own | `test_system_never_sends_an_alert_on_its_own` (morning, archetypes, lost vehicle, flood) |
| Hot reload changes decisions without a restart; same seed + new config gives a correct diff | `test_hot_reload_changes_live_decisions_and_twist_diff_matches_replays`, `test_same_seed_new_config_preview_is_repeatable`, `test_file_edit_hot_reloads_and_bad_edit_keeps_last_good` |
| Jurisdiction profiles switch via config only | `test_jurisdiction_profiles_switch_by_config_only` (LA, Singapore, EU: recipient, channel, language, windows, registry) |
| Flood finishes in reasonable time; budget adds up | `test_flood_is_fast_and_budget_adds_up` (240 s of flood in about 4 s through the hub) |
| Dual-use runs through the same engine with different labels and actions | `test_dual_use_runs_the_same_engine_with_recovery_wording`, `test_mode_switch_loads_recovery` |
| Replay determinism | `test_scenarios_are_deterministic`, `test_random_runs_replay_identically`, `test_replay_with_rule_advisor_is_deterministic_through_the_api` |

**Live path:** I started the server and ran the demo scenarios through the real HTTP API (`live_check.py` in the session scratchpad); all checks passed.
- **Stream:** SSE sends `hello` and then ticks every 0.5 s, including in the flood.
- **Morning watch:** 2 items wait for the operator. `send` before `approve` returns 409; approve and then send works. The advisor raised C-107 to Slow.
- **Flood:** 200 contacts, 198 quiet, 2 need the operator.
- **Lost vehicle:** found and drafted to the Wrigley ops desk.
- **Seeded random:** seed 4242 replays identically.
- **Jurisdiction:** a twist to the EU profile drafts a Dutch notice to Kustwacht, and reverting returns to LA.
- **Audit:** the audit log records advisor calls.

## 3. STILL BROKEN OR RISKY

- **The LLM advisor blocks the sim tick on a cache miss** (`backend/app/session.py` `evaluate`, under the hub lock in `hub.py`). This can stall up to 3 s per call. It is safe with the rule-based default and not safe to enable live without prefetching.
- **Twist previews with the LLM enabled are slow** (`backend/app/twists.py` `preview`). The "after" run has a new config hash, so every ambiguous snapshot is a new serial call.
- **The LLM transport has never hit the real API** (`advisor.py` `anthropic_transport`). There's no key here; the parsing and guardrails are tested with stubs.
- **Only a mock classifier exists** (`backend/app/classifier.py`). `Observation` still carries sim-only `truth` and `label_track`.
- **Operator approval is not authenticated** (`backend/app/main.py` `/api/handoff`). The approval step is enforced, but the operator is a free-text name.
- **CPA assumes a straight line** (`backend/app/facts.py` `closest_approach`). It misjudges waypoint followers and turning contacts.
- **The Singapore and EU profiles use placeholder recipients, channels, windows and registries** (`config/rules.yaml`). Under them, recovery mode cannot find REMUS-02, because the lost vehicle is not in their registries.
- **The UI does not show the new fields** (`frontend/src`). Per instructions only the data was added. The advisor's note does appear inside the decision reason text ("Advisor: …"). The Alert Budget card still shows the live pending count, not `needed_operator`.

## 4. NEEDS MY INPUT

1. **Enable the LLM advisor?** Recommended default: **no** for the live demo. Keep `advisor.backend: rule` until the tick no longer waits on the network.
2. **Which model and key, if you do?** Recommended: `claude-haiku-5-5` via `ANTHROPIC_API_KEY`, timeout 2.5 s. It is the fastest Claude option.
3. **Keep Singapore and EU as demo examples, or replace them with verified details?** Recommended: keep them only as a "config switch" talking point, and send me real recipients, channels and windows if a judge will probe.
4. **How eager should the advisor be?** Recommended: keep `raise_at: 0.6` and `max_raise: 1`. Lower values raise more contacts and can put C-112 into Hold before the Fuel Dock B twist.
5. **CPA cap?** Recommended: keep `consequence.cpa.raise_to: medium`, so a course into a band makes us Ask rather than Hold. `high` would send fast-approaching contacts to a person earlier.
6. **Should the Alert Budget card show cumulative "needed you" (adds up to the total) or the live queue (today)?** Recommended: keep the live queue and add "of N" later. That is a UI change, so I held off.
7. **Show `ai_reason` as its own line in receipts and the hand-off sheet?** Recommended: yes, as one small "Advisor raised: …" line. That is a UI change, so I held off.
8. **Merge order?** This branch is built on `random-scenarios`, which is not on `main` yet. Recommended: merge `pipeline-audit` (it includes both).

## 5. NEEDS ME TO DO

Nothing is required for the demo. Everything runs offline with no keys.

Optional, to try the LLM advisor:

```bash
export ANTHROPIC_API_KEY=your-key            # never commit it; .env files are gitignored
# then in config/rules.yaml: advisor.backend: llm   (hot-reloads, no restart)
rm -f data/advisor_cache.json                # whenever you change model or prompt
```

To publish this work:

```bash
git push -u origin pipeline-audit
git push origin pre-audit v3-audited
gh pr create --base main --head pipeline-audit --title "Pipeline audit: advisor layer, CPA, jurisdictions"
```

## 6. DEMO READINESS

- [x] **Morning watch.** Safe. C-107 now goes Ask → Slow (advisor) → Hold + Hand off, a good "where's the AI" moment. C-108 evades into an urgent hand-off as before.
- [x] **Fuel Dock B twist** (edit `rules.yaml` or use the preset). Safe. C-112 still goes Slow → Hold + Hand off.
- [x] **Flood (200).** Safe. 198 quiet, 2 need you, ticks steady.
- [x] **Dual-use / lost REMUS-02.** Safe. It is now pinged a little earlier (advisor), then found and drafted to the owner.
- [x] **"+" random scenarios and Replay.** Safe. All three risk tiers are always present and the replay is identical.
- [x] **Approve → send** to the mock outbox. Safe.
- [ ] **LLM advisor live.** Avoid. It can stall the tick.
- [ ] **Singapore / EU profiles.** Script around them: show the one-line switch and the Dutch draft, but don't present the details as verified. Switch back to `la` before recovery mode.
- [ ] **Twist preview on the flood at 5×.** Works, but takes about 3 s. Pause first if you show it.

## 7. FOR THE BACKEND TEAMMATE

`BACKEND_NOTES.md` now has "Advisor layer (AI)", "Consequence look-ahead" and "Jurisdictions" sections covering the points in section 3, with TODOs: prefetch LLM advice off the tick, batch preview calls, cache-key versioning, curved-path CPA, per-profile recovery vehicle, and operator authentication.

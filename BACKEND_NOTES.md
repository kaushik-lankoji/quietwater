# Backend notes · what to harden next

The backend is built so the demo is reliable and so twists are config changes. It is not production-hardened. Here is what I know is weak, roughly in priority order.

## State and persistence

- **All live state is in memory** (`Hub`: receipts, hand-off items, audit log, outbox). A restart loses it. Only twist history (`data/twist_history.json`) and `config/rules.yaml` persist. TODO: an append-only store (SQLite to start) for audit + receipts, ideally hash-chained so the audit log is tamper-evident.
- **Twist history is a JSON file rewritten on every add** and keeps the full pre-change YAML for revert. It grows unbounded. TODO: move it into the same store; keep snapshots by content hash.
- **Audit export** reads the in-memory deque (max 50k entries). Older entries silently fall off.

## Concurrency

- **The sim tick runs inside the asyncio loop** under a coarse `threading.RLock`. A 200-contact tick is ~10 ms, fine for the demo, but it blocks request handling while it runs. TODO: move the simulator/engine into a worker process and publish snapshots.
- **Twist previews run in the threadpool** and replay the scenario twice (about 1.5 s for the flood). They share the GIL with the tick, so the UI can stutter during a flood preview. TODO: a process pool, plus caching of the "before" run per rules version.
- **Thread → loop handoff** for broadcasts uses `call_soon_threadsafe`. Keep that if you refactor; touching the `asyncio.Queue`s from a thread is not safe.

## Streaming

- **Every tick sends a full snapshot** over SSE (~60–100 KB at 200 contacts, 2 Hz). Slow clients drop the oldest messages (queue size 20). TODO: send diffs, gzip, or move to WebSocket with a version number per contact.
- No `Last-Event-ID` resume. A reconnect gets a fresh `hello`, which is fine but heavy.

## Rules and hot reload

- **Hot reload is mtime polling every tick.** Two quick saves within the filesystem's mtime resolution could be missed. TODO: `watchfiles`, plus a content hash instead of mtime.
- **Writes from the UI** go through ruamel round-trip. Comments survive scalar edits; a list that changes length is replaced wholesale and loses its inline comments.
- **No file lock.** An operator saving in an editor while the UI applies a twist can race (last write wins; both are validated).
- **The schema validates shape and a few invariants** (human floor ≤ R4, registry zones exist, band ordering). It does not check that the ladder is monotone (e.g. `unknown_high` mapped lower than `unknown_low`). TODO: add sanity warnings rather than hard errors.
- Twist endpoints accept arbitrary YAML/JSON. The safe loader is used, but there is no size cap. TODO: limit request bodies.

## Engine and simulator

- **Urgent R5 latching never clears on its own.** That's intended for the demo, but it needs an explicit operator "clear / resolved" action.
- **Evasion detection is a heuristic:** turn sum or speed jump after the hail. A random contact that bounces off land after being hailed can look evasive. The scripted scenarios avoid this.
- **Preview vs live drift:** previews step at 1 s (2 s for >60 contacts), while live steps at `0.5 s × speed`. Motion and evasion sampling differ slightly, so a preview is a faithful replay of the scenario but not frame-identical to what is on screen.
- **Hand-off windows run on sim time.** At 10× a 5-minute window lasts 30 real seconds. Correct for replay, wrong for production; use wall time there.
- **A hand-off item re-opens only if severity increases.** An approved item stays closed while the contact keeps the same rung.
- **Random scenarios** (`random_harbor`, `random_recovery`) are built by `app/randomizer.py` from the `randomizer:` block in `config/scenarios.yaml`. No new endpoint: the UI calls the existing `POST /api/sim/scenario` with `{name, seed}`, and Replay reuses the session seed. Generation reads only the seed and the static scenario config, never `rules.yaml`, so a seed gives the same contacts before and after a twist and the preview diff compares like with like. Each scenario always has one low, one mid and one high contact: the `required` slot groups are placed in regions chosen so default rules land them in those tiers (tests check 25 seeds per mode; 200 per mode were checked by hand). A twist that moves bands or assets can legitimately change that.
- **The tier guarantee depends on placement regions** (`ship_medium`, `fuel_dock`, `ship_close`, …) drawn for the current harbor and asset layout. Moving an asset in `rules.yaml` does not move the regions. TODO: derive regions from asset geometry and consequence bands at generation time, using the defaults rather than live rules to keep determinism.
- Only the mock classifier exists. Add a real model by implementing the `Classifier` protocol and registering it in `build_classifier`.

## Advisor layer (AI)

- **An LLM call blocks the tick.** `Session.evaluate` runs under the hub lock, so a cache miss with `advisor.backend: llm` can stall the sim and the API for up to `advisor.timeout_s` (3 s). The rule-based default is microseconds. TODO before enabling the LLM live: prefetch advice off the tick (enqueue ambiguous snapshots, apply the cached answer on a later tick) so the tick never waits on the network.
- **Twist previews with the LLM are slow.** The "after" run has a new config hash, so every ambiguous snapshot is a fresh call, made serially. TODO: batch calls, or preview with the rule-based advisor and label it as such.
- **Timed-out calls keep a worker thread** until urllib's own timeout fires (pool of 4). If all four hang, further calls time out immediately and fall back to the rule-based advisor. Safe, but noisy in the logs.
- **The LLM transport was tested live once** (`backend/scripts/llm_smoke.py`, `claude-haiku-5-5`). Findings: the API rejects `temperature` for this model, and the model "thinks" by default, which used up the 200-token budget and added about 1 s, so the request sets `thinking: disabled` (about 1 s per call, strict JSON came back every time). A request-shape regression test pins this.
- **Live measurement, morning watch, 120 sim-seconds:** 12 advisor calls, worst single tick 4.35 s (several cache misses in one tick, made one after another), replay from cache identical with a 0.00 s worst tick.
- **The model is much more eager than the rule-based advisor.** It raised C-106, C-110 (a registered-type survey ROV), C-111 (marine life at 62%) and C-112, and pushed C-112 to Hold + Hand off before the Fuel Dock B twist. With the LLM on, the demo story changes. TODO: tighten the system prompt (raise only when it can name a concrete compounding signal) and measure again before using it in front of judges.
- **The cache is per process plus `data/advisor_cache.json`** (LLM answers only). It is not size-bounded on disk; the in-memory LRU is capped at 20k entries. Changing the model or prompt does not change the cache key; clear the file when you do.
- **Ambiguity weights are hand-tuned** (`advisor.weights`, `raise_at: 0.6`). With the defaults the advisor raises C-107 in the morning watch (closing, silent, low confidence) and leaves C-112 alone, so the Fuel Dock B twist still lands. Re-check the demo if you tune them.

## Consequence look-ahead

- **CPA assumes a straight line** at the current heading and speed over `consequence.cpa.horizon_s` (120 s, 5 s steps). Waypoint followers and turning contacts are under- or over-estimated. It roughly doubles per-contact cost: a headless 240-step flood run went from 1.6 s to 3.1 s, and a live flood tick is about 16 ms (well inside the 500 ms tick).
- **The trend window depends on the trail.** Live ticks keep 40 s of trail at 1×; previews step at 1 s and keep 80 s. Trends are computed over 30 s so both agree, but contacts younger than 27 s are `new`.

## Jurisdictions

- **The Singapore and EU profiles are illustrative.** The recipients, channels, windows and registry entries are plausible placeholders, not checked with MPA or Rotterdam. The harbor geometry is still LA.
- **A profile with its own registry hides the base registry.** Under `singapore` or `eu`, USC-REMUS-01/02 are unknown, so recovery mode finds no lost vehicle (the recovery target must be in the active registry). Give each profile its own `recovery.lost_vehicle_id` if this matters.
- **The Twist Console's schedule editor edits the base `registry` only,** not a profile's registry.

## Security and ops

- **No authentication.** The operator name is a free string from the client, so "operator approval" for R4/R5 is enforced as a step but not tied to a verified person. TODO: OIDC login, roles (watch officer vs supervisor), and approvals signed with user identity.
- CORS allows only the Vite dev origins. The production build is same-origin.
- The SPA catch-all route checks for path traversal (`DIST in file.resolve().parents`); re-verify it if you change static serving.
- **The outbox is a mock** and never transmits. Keep any real Coast Guard integration operator-initiated. That is a product promise, not just a TODO.
- No metrics or structured logs. TODO: tick duration, queue depth, SSE clients, preview latency.

## Tests

- 123 backend tests (engine branches, loop cap, advisor guardrails, end-to-end pipeline, sim determinism, random-scenario tiers and replay, API flows). No load test and no frontend tests yet.
- TODO: a property test that `confidence alone never escalates` holds for random facts; a soak test of the flood at 5× for 30 minutes; Playwright smoke tests for approve → send and preset → apply.

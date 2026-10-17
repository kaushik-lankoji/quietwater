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
- `PretrainedClassifier` is a stub with `features()` and a `label_map`. Wire a real model behind `classifier.backend: pretrained`.

## Security and ops

- **No authentication.** The operator name is a free string from the client. TODO: OIDC login, roles (watch officer vs supervisor), and approvals signed with user identity.
- CORS allows only the Vite dev origins. The production build is same-origin.
- The SPA catch-all route checks for path traversal (`DIST in file.resolve().parents`); re-verify it if you change static serving.
- **The outbox is a mock** and never transmits. Keep any real Coast Guard integration operator-initiated. That is a product promise, not just a TODO.
- No metrics or structured logs. TODO: tick duration, queue depth, SSE clients, preview latency.

## Tests

- 69 backend tests (engine branches, loop cap, sim determinism, API flows). No load test and no frontend tests yet.
- TODO: a property test that `confidence alone never escalates` holds for random facts; a soak test of the flood at 10× for 30 minutes; Playwright smoke tests for approve → send and preset → apply.

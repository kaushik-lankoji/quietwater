import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { Toasts, useToasts } from "./components/bits";
import { BudgetCard } from "./components/BudgetCard";
import { DualUseToggle } from "./components/DualUseToggle";
import { HandoffSheetBody, isWaiting, needsAttention, type ActExtra } from "./components/HandoffSheet";
import { Icon } from "./components/Icon";
import { OptimizationPanel } from "./components/OptimizationPanel";
import { Radar } from "./components/Radar";
import { ReceiptsSheetBody } from "./components/ReceiptsSheet";
import { ScenarioButton } from "./components/ScenarioButton";
import { Sheet } from "./components/Sheet";
import { WatchPanel } from "./components/WatchPanel";
import { TwistConsole } from "./components/TwistConsole";
import type { Config, Contact, HandoffAction, HandoffItem, ItemStatus } from "./types";
import { useLive } from "./useLive";

type SheetName = "handoff" | "receipts" | "twist";

const OPERATOR = "Watch officer";
const HANDLED: ItemStatus[] = ["hold_requesting", "hold_active", "notice_sent", "dismissed", "resolved", "lifted", "stood_down"];
const FLOOD = "flood";

const newSeed = () => crypto.getRandomValues(new Uint32Array(1))[0] % 1_000_000;

export default function App() {
  const { snap, receipts, history, link } = useLive();
  const [config, setConfig] = useState<Config | null>(null);
  const [sheet, setSheet] = useState<SheetName | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const [managing, setManaging] = useState<string | null>(null);
  const [receiptFocus, setReceiptFocus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { toasts, push } = useToasts();
  const lastVersion = useRef<number | null>(null);
  const seenPending = useRef<Set<string> | null>(null);

  const version = snap?.rules.version;
  useEffect(() => {
    if (version === undefined || version === lastVersion.current) return;
    const first = lastVersion.current === null;
    lastVersion.current = version;
    api
      .config()
      .then((c) => {
        setConfig(c);
        if (!first) push(`Rules reloaded · v${c.version}`, "ok");
      })
      .catch((e: Error) => push(e.message, "error"));
  }, [version, push]);

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn();
      } catch (e) {
        push((e as Error).message, "error");
      } finally {
        setBusy(false);
      }
    },
    [push],
  );

  // A red contact turns gray once its latest hand-off is dismissed, stood down, or acted on.
  const handledKey = useMemo(() => {
    const latest = new Map<string, HandoffItem>();
    for (const i of snap?.items ?? []) {
      const prev = latest.get(i.contact_id);
      if (!prev || i.created_t > prev.created_t || (i.created_t === prev.created_t && i.id > prev.id)) latest.set(i.contact_id, i);
    }
    return [...latest.values()].filter((i) => HANDLED.includes(i.status)).map((i) => i.contact_id).sort().join(",");
  }, [snap?.items]);
  const handled = useMemo<ReadonlySet<string>>(() => new Set(handledKey ? handledKey.split(",") : []), [handledKey]);

  // Contacts on the watch list are drawn blue, like they are being watched.
  const watchedKey = (snap?.items ?? []).filter((i) => i.status === "watching").map((i) => i.contact_id).sort().join(",");
  const watched = useMemo<ReadonlySet<string>>(() => new Set(watchedKey ? watchedKey.split(",") : []), [watchedKey]);

  // An active area hold blocks off a region around its contact, not just the contact's dot.
  const holdsKey = (snap?.items ?? [])
    .filter((i) => i.hold?.scope === "area" && i.hold.status === "active")
    .map((i) => `${i.contact_id}:${i.hold?.radius_m ?? config?.rules.handoff?.area_radius_m ?? 400}`)
    .join(",");
  const holds = useMemo(
    () => (holdsKey ? holdsKey.split(",").map((k) => ({ id: k.split(":")[0], radiusM: Number(k.split(":")[1]) })) : []),
    [holdsKey],
  );

  const queue = useMemo(() => (snap ? snap.items.filter(needsAttention) : []), [snap]);
  // Stay on the chosen item while it is still in the queue; once it is finished, move to the next one.
  const active = queue.find((i) => i.id === activeItem) ?? queue[0];

  useEffect(() => {
    if (!snap) return;
    const pending = snap.items.filter(isWaiting);
    const seen = seenPending.current;
    seenPending.current = new Set(pending.map((i) => i.id));
    if (!seen) return;
    const fresh = pending.find((i) => !seen.has(i.id) && i.decision.urgency === "urgent");
    if (fresh && sheet === null) {
      setActiveItem(fresh.id);
      setSheet("handoff");
    }
  }, [snap, sheet]);

  const act = useCallback(
    (item: HandoffItem, action: HandoffAction, extra?: ActExtra) =>
      run(async () => {
        setActiveItem(item.id);
        await api.act(item.id, action, OPERATOR, extra);
        const verb: Partial<Record<HandoffAction, string>> = {
          approve: "Hold requested",
          retry: "Hold requested again",
          send: `Notice sent to ${item.draft?.to ?? "agency"}`,
          dismiss: "Dismissed",
          undo: "Back in your queue",
          watch: "Watching",
          escalate: "Escalated",
          lift: "Hold lifted",
          resolve: "Resolved",
          extend: "Hold extended",
          edit: "Notice updated",
        };
        if (verb[action]) push(`${verb[action]} · ${item.contact_id}`, "ok");
      }),
    [run, push],
  );

  const toggleSheet = useCallback((name: SheetName) => setSheet((s) => (s === name ? null : name)), []);

  const togglePause = useCallback(() => {
    if (snap) run(() => api.control(snap.running ? "pause" : "play"));
  }, [snap, run]);
  const replay = useCallback(() => run(() => api.control("restart")), [run]);
  const flood = useCallback(() => run(() => api.scenario(FLOOD)), [run]);
  const loadScenario = useCallback(
    (id: string) => {
      const random = config?.scenarios.find((s) => s.id === id)?.random;
      setSelected(null);
      run(() => api.scenario(id, random ? newSeed() : undefined));
    },
    [config, run],
  );
  // Push a new red contact onto the live radar.
  const [pulseFor, setPulseFor] = useState<{ ids: string[]; n: number } | null>(null);
  const addRed = useCallback(
    () => run(async () => setPulseFor({ ids: (await api.inject(1)).ids, n: Date.now() })),
    [run],
  );
  // Re-roll the scenario that is already selected. The choice of scenario never changes.
  const randomize = useCallback(() => {
    if (!snap) return;
    setSelected(null);
    run(() => api.scenario(snap.scenario.id, newSeed()));
  }, [snap, run]);

  const onSelect = useCallback(
    (c: Contact | null) => {
      setSelected(c?.id ?? null);
      if (!c || !snap) return;
      const human = c.requires_human || c.rung === "R4" || c.rung === "R5";
      const items = snap.items.filter((i) => i.contact_id === c.id);
      const item = items.find(needsAttention);
      if (human && item) {
        setActiveItem(item.id);
        setSheet("handoff");
      } else {
        setReceiptFocus(c.id);
        setSheet("receipts");
      }
    },
    [snap],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase();
      if (key === "escape") return setSheet(null);
      if (key === " ") {
        if (t.tagName === "BUTTON") return;
        e.preventDefault();
        return togglePause();
      }
      if (key === "r") return replay();
      if (key === "f") return flood();
      if (key === "t") return toggleSheet("twist");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePause, replay, flood, toggleSheet, sheet, active, busy, act]);

  if (!snap || !config) {
    return (
      <div className="app loading">
        <span className="spinner" />
        <span>{link === "lost" ? "Waiting for the Quietwater server on :8000" : "Connecting to the harbor"}</span>
      </div>
    );
  }

  const recovery = snap.mode === "recovery";

  return (
    <div className="app">
      <Radar contacts={snap.contacts} run={snap.run} selected={selected} handled={handled} watched={watched} holds={holds} pulseFor={pulseFor}
        rangeM={snap.scenario.coverage_radius_m} onSelect={onSelect} />

      <BudgetCard
        budget={snap.budget}
        clock={snap.clock}
        scenario={snap.scenario.id}
        seed={snap.scenario.seed}
        trafficLevel={snap.scenario.traffic_level}
        coverageRadiusM={snap.scenario.coverage_radius_m}
        scenarios={config.scenarios}
        link={link}
        onScenario={loadScenario}
        onOpen={() => toggleSheet("handoff")}
      />

      <WatchPanel
        items={snap.items}
        active={sheet === "handoff" ? (active?.id ?? null) : null}
        onOpen={(id) => {
          setActiveItem(id);
          setSheet("handoff");
        }}
      />

      <DualUseToggle on={recovery} onChange={(on) => run(() => api.mode(on ? "recovery" : "security"))} />

      {snap.rules.error && (
        <div className="banner glass" role="alert">
          <Icon name="alert" size={18} />
          <span>
            <strong>rules.yaml has an error.</strong> Still running on v{snap.rules.version}. {snap.rules.error}
          </span>
        </div>
      )}

      <Sheet
        open={sheet === "handoff"}
        flush
        title={active ? `Contact ${active.contact_id}` : "All clear"}
        onClose={() => setSheet(null)}
      >
        <HandoffSheetBody active={active} rules={config.rules} onAct={act} busy={busy} quiet={snap.budget.quiet} managing={managing} onManage={setManaging} />
      </Sheet>

      <Sheet open={sheet === "receipts"} flush title="Decision receipts" onClose={() => setSheet(null)}>
        <ReceiptsSheetBody receipts={receipts} focus={receiptFocus} onFocus={setReceiptFocus} />
      </Sheet>

      <Sheet open={sheet === "twist"} title="Twist Console" onClose={() => setSheet(null)}>
        <TwistConsole config={config} snap={snap} history={history} toast={push} />
      </Sheet>

      <ScenarioButton onClick={randomize} />
      <button type="button" className="red-button" title="Push a new red contact onto the radar" onClick={addRed}>
        <Icon name="plus" size={20} />
        New red contact
      </button>
      <OptimizationPanel metrics={snap.optimization} />
      <Toasts toasts={toasts} />
    </div>
  );
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { Toasts, useToasts } from "./components/bits";
import { BudgetCard } from "./components/BudgetCard";
import { ControlDock } from "./components/ControlDock";
import { DualUseToggle } from "./components/DualUseToggle";
import { HandoffSheetBody, needsAttention, type Action } from "./components/HandoffSheet";
import { Icon } from "./components/Icon";
import { Radar } from "./components/Radar";
import { ReceiptsSheetBody } from "./components/ReceiptsSheet";
import { ScenarioButton } from "./components/ScenarioButton";
import { Sheet } from "./components/Sheet";
import { TwistConsole } from "./components/TwistConsole";
import type { Config, Contact, HandoffItem } from "./types";
import { useLive } from "./useLive";

type SheetName = "handoff" | "receipts" | "twist";

const OPERATOR = "Watch officer";
const FLOOD = "flood";

export default function App() {
  const { snap, receipts, history, link } = useLive();
  const [config, setConfig] = useState<Config | null>(null);
  const [sheet, setSheet] = useState<SheetName | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<string | null>(null);
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

  const queue = useMemo(() => (snap ? snap.items.filter(needsAttention) : []), [snap]);
  const active = (snap?.items.find((i) => i.id === activeItem) ?? queue[0]) as HandoffItem | undefined;

  useEffect(() => {
    if (!snap) return;
    const pending = snap.items.filter((i) => i.status === "pending");
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
    (item: HandoffItem, action: Action) =>
      run(async () => {
        await api.act(item.id, action, OPERATOR);
        const verb = { approve: "Approved", reject: "Rejected", watch: "Watching", send: "Alert sent" }[action];
        push(`${verb} · ${item.contact_id}`, "ok");
      }),
    [run, push],
  );

  const toggleSheet = useCallback((name: SheetName) => setSheet((s) => (s === name ? null : name)), []);

  const togglePause = useCallback(() => {
    if (snap) run(() => api.control(snap.running ? "pause" : "play"));
  }, [snap, run]);
  const replay = useCallback(() => run(() => api.control("restart")), [run]);
  const flood = useCallback(() => run(() => api.scenario(FLOOD)), [run]);

  const openReceipts = useCallback(() => {
    setReceiptFocus(null);
    toggleSheet("receipts");
  }, [toggleSheet]);

  const onSelect = useCallback(
    (c: Contact | null) => {
      setSelected(c?.id ?? null);
      if (!c || !snap) return;
      const human = c.requires_human || c.rung === "R4" || c.rung === "R5";
      const items = snap.items.filter((i) => i.contact_id === c.id);
      const item = items.find(needsAttention) ?? items[0];
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
      if (key === "a" && sheet === "handoff" && active && !busy && (active.status === "pending" || active.status === "watching")) act(active, "approve");
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
  const pending = queue.filter((i) => i.status === "pending").length;
  const automated = receipts.filter((r) => r.automated).length;

  return (
    <div className="app">
      <Radar contacts={snap.contacts} run={snap.run} selected={selected} onSelect={onSelect} />

      <BudgetCard
        budget={snap.budget}
        clock={snap.clock}
        scenario={snap.scenario.id}
        scenarios={config.scenarios}
        link={link}
        onScenario={(id) => run(() => api.scenario(id))}
        onOpen={() => toggleSheet("handoff")}
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

      <Sheet open={sheet === "handoff"} flush title="Needs you" meta={`${pending} waiting · ${snap.budget.quiet} handled quietly`} onClose={() => setSheet(null)}>
        <HandoffSheetBody
          items={snap.items}
          rules={config.rules}
          activeId={active?.id ?? null}
          onActive={setActiveItem}
          onAct={act}
          busy={busy}
          quiet={snap.budget.quiet}
        />
      </Sheet>

      <Sheet open={sheet === "receipts"} flush title="Decision receipts" meta={`${receipts.length} logged · ${automated} automated`} onClose={() => setSheet(null)}>
        <ReceiptsSheetBody receipts={receipts} focus={receiptFocus} onFocus={setReceiptFocus} />
      </Sheet>

      <Sheet open={sheet === "twist"} title="Twist Console" meta={`Live rules v${config.version} · no code, no restart`} onClose={() => setSheet(null)}>
        <TwistConsole config={config} snap={snap} history={history} toast={push} />
      </Sheet>

      <ControlDock
        running={snap.running}
        flood={snap.scenario.id === FLOOD}
        sheet={sheet}
        onToggleRun={togglePause}
        onReplay={replay}
        onFlood={flood}
        onReceipts={openReceipts}
      />

      <ScenarioButton />
      <Toasts toasts={toasts} />
    </div>
  );
}

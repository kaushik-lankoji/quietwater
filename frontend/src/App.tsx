import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { AlertBudget } from "./components/AlertBudget";
import { Toasts, useToasts } from "./components/bits";
import { HandoffPanel, needsAttention, type Action } from "./components/HandoffPanel";
import { HarborMap, type Layers } from "./components/HarborMap";
import { Icon } from "./components/Icon";
import { Inspector } from "./components/Inspector";
import { Receipts } from "./components/Receipts";
import { TopBar } from "./components/TopBar";
import { TwistConsole } from "./components/TwistConsole";
import { cls, rungVar } from "./format";
import { RUNGS, type Config, type Decision, type HandoffItem } from "./types";
import { useLive } from "./useLive";

type View = "watch" | "twist";
type Theme = "dark" | "light";

const OPERATOR = "Watch officer";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("qw-theme");
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export default function App() {
  const { snap, receipts, history, link } = useLive();
  const [config, setConfig] = useState<Config | null>(null);
  const [view, setView] = useState<View>("watch");
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [selected, setSelected] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [layers, setLayers] = useState<Layers>({ zones: true, trails: true, labels: true });
  const [receiptsCollapsed, setReceiptsCollapsed] = useState(() => {
    try {
      return localStorage.getItem("qw-receipts") === "collapsed";
    } catch {
      return false;
    }
  });
  const { toasts, push } = useToasts();
  const lastVersion = useRef<number | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("qw-theme", theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);

  useEffect(() => {
    if (snap) document.documentElement.dataset.mode = snap.mode;
  }, [snap?.mode]);

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
  const active = queue.find((i) => i.id === activeItem) ?? queue[0];

  const act = useCallback(
    (item: HandoffItem, action: Action) =>
      run(async () => {
        await api.act(item.id, action, OPERATOR);
        const verb = { approve: "Approved", reject: "Rejected", watch: "Watching", send: "Alert sent" }[action];
        push(`${verb} · ${item.contact_id}`, "ok");
      }),
    [run, push],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === " " && snap) {
        e.preventDefault();
        run(() => api.control(snap.running ? "pause" : "play"));
        return;
      }
      if (view !== "watch" || !active || busy) return;
      const open = active.status === "pending" || active.status === "watching";
      const map: Record<string, Action> = { a: "approve", r: "reject", w: "watch" };
      const action = map[e.key.toLowerCase()];
      if (action && open) act(active, action);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [snap, view, active, busy, act, run]);

  const latestDecision = useMemo(() => {
    const out = new Map<string, Decision>();
    for (const r of receipts) out.set(r.contact_id, r.decision);
    return out;
  }, [receipts]);

  if (!snap || !config) {
    return (
      <div className="empty" style={{ height: "100%" }}>
        <span className="spinner" />
        <span>{link === "lost" ? "Waiting for the Quietwater server on :8000…" : "Connecting to the harbor…"}</span>
      </div>
    );
  }

  const texts = config.rules.modes[snap.mode];
  const selectedContact = selected ? snap.contacts.find((c) => c.id === selected) : undefined;
  const focus = active ? { contactId: active.contact_id, asset: active.decision.focus_asset } : null;
  const pending = queue.filter((i) => i.status === "pending").length;

  return (
    <div className="app">
      <TopBar
        snap={snap}
        config={config}
        link={link}
        theme={theme}
        onTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        onControl={(action, speed) => run(() => api.control(action, speed))}
        onScenario={(id, seed) => run(() => api.scenario(id, seed))}
        onMode={(recovery) => run(() => api.mode(recovery ? "recovery" : "security"))}
      />
      <div>
        <nav className="tabs" role="tablist" aria-label="Views">
          <button className="tab" role="tab" aria-selected={view === "watch"} onClick={() => setView("watch")}>
            Watch
            <span className={cls("count", pending > 0 && "hot")}>{pending}</span>
          </button>
          <button className="tab" role="tab" aria-selected={view === "twist"} onClick={() => setView("twist")}>
            Twist Console
            {history.length > 0 && <span className="count">{history.length}</span>}
          </button>
          <div className="tabs-right muted">
            <span className="mono">rules v{snap.rules.version}</span>
            <span>A approve · R reject · W keep watching · Space pause</span>
          </div>
        </nav>
        {snap.rules.error && (
          <div className="banner error" role="alert">
            <Icon name="alert" />
            <span>
              <strong>rules.yaml has an error.</strong> Still running on v{snap.rules.version}. {snap.rules.error}
            </span>
          </div>
        )}
        {snap.mode === "recovery" && (
          <div className="banner recovery">
            <Icon name="wave" />
            <span>
              <strong>Second customer: {texts.customer}.</strong> {snap.scenario.description}
            </span>
          </div>
        )}
      </div>
      <main>
        {view === "watch" ? (
          <div className={cls("watch", receiptsCollapsed && "receipts-collapsed")}>
            <AlertBudget budget={snap.budget} texts={texts} />
            <HarborMap
              harbor={config.harbor}
              rules={config.rules}
              contacts={snap.contacts}
              selected={selected}
              onSelect={setSelected}
              focus={focus}
              layers={layers}
            >
              <div className="map-overlay top-left">
                <div className="glass map-title" title={snap.scenario.description}>
                  <strong>{snap.scenario.title}</strong>
                </div>
              </div>
              <div className="map-overlay top-right">
                <div className="glass layer-toggles" role="group" aria-label="Map layers">
                  {(Object.keys(layers) as (keyof Layers)[]).map((k) => (
                    <button key={k} aria-pressed={layers[k]} onClick={() => setLayers((l) => ({ ...l, [k]: !l[k] }))}>
                      {k[0].toUpperCase() + k.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
              <div className="map-overlay bottom-right">
                <div className="glass legend" aria-label="Legend">
                  {RUNGS.map((r) => (
                    <span key={r}>
                      <i style={{ background: rungVar(r) }} />
                      {texts.rungs[r].name}
                    </span>
                  ))}
                </div>
              </div>
              {selectedContact && (
                <div className="map-overlay bottom-left">
                  <Inspector
                    contact={selectedContact}
                    decision={latestDecision.get(selectedContact.id)}
                    onClose={() => setSelected(null)}
                  />
                </div>
              )}
            </HarborMap>
            <div className="rail">
              <HandoffPanel
                items={snap.items}
                rules={config.rules}
                activeId={active?.id ?? null}
                onActive={setActiveItem}
                onAct={act}
                busy={busy}
                quiet={snap.budget.quiet}
              />
            </div>
            <Receipts
              receipts={receipts}
              onSelect={setSelected}
              collapsed={receiptsCollapsed}
              onCollapse={(v) => {
                setReceiptsCollapsed(v);
                try {
                  localStorage.setItem("qw-receipts", v ? "collapsed" : "open");
                } catch {
                  /* storage unavailable */
                }
              }}
            />
          </div>
        ) : (
          <TwistConsole config={config} snap={snap} history={history} toast={push} />
        )}
      </main>
      <Toasts toasts={toasts} />
    </div>
  );
}

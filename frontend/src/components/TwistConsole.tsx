import { useEffect, useMemo, useState } from "react";
import { api, type PreviewResult, type TwistPayload } from "../api";
import { cls, display } from "../format";
import type { Config, ImpactRow, Preset, RulesData, Snapshot, TwistEntry } from "../types";
import { Rungs, useDebounced } from "./bits";
import { Icon } from "./Icon";
import { LadderEditor, ScheduleEditor, setIn, ThresholdsEditor, ZonesEditor, type PathKey } from "./TwistEditors";

type Tab = "thresholds" | "ladder" | "zones" | "schedule" | "yaml";

const TABS: [Tab, string][] = [
  ["thresholds", "Thresholds"],
  ["ladder", "Rungs"],
  ["zones", "Zones"],
  ["schedule", "Schedule"],
  ["yaml", "YAML"],
];

function Delta({ before, after, invert }: { before: number; after: number; invert?: boolean }) {
  const dir = after > before ? "up" : after < before ? "down" : "";
  const cls_ = invert ? (dir === "up" ? "down" : dir === "down" ? "up" : "") : dir;
  return (
    <div className="n num">
      <span>{before}</span>
      <span className="arrow">→</span>
      <span className={cls_}>{after}</span>
    </div>
  );
}

function DiffRow({ row }: { row: ImpactRow }) {
  const b = row.before;
  const a = row.after;
  const timing = row.first_human_t.before !== row.first_human_t.after && row.first_human_t.before !== null && row.first_human_t.after !== null;
  return (
    <div className="diff-row">
      <div className="diff-head">
        <span className="cid">{row.contact_id}</span>
        <span className="muted">{row.label}</span>
        {row.direction !== "same" && <span className={cls("direction", row.direction)}>{row.direction}</span>}
      </div>
      <div className="transition">
        {b ? <Rungs rungs={b.rungs} names={b.rung_names} /> : <span className="muted">not seen</span>}
        <Icon name="chevronRight" size={14} />
        {a ? <Rungs rungs={a.rungs} names={a.rung_names} /> : <span className="muted">not seen</span>}
      </div>
      {a && b && a.requires_human !== b.requires_human && (
        <span className="after-reason">
          <strong>{a.requires_human ? "Now needs a person." : "No longer needs a person."}</strong>
        </span>
      )}
      {a && b && a.path.join() !== b.path.join() && (
        <span className="after-reason num">
          path {b.path.join("›")} → {a.path.join("›")}
        </span>
      )}
      {a && (
        <span className="after-reason">
          {a.reason}
          {timing && (
            <>
              {" "}
              Asks a person at t={row.first_human_t.after}s (was {row.first_human_t.before}s).
            </>
          )}
        </span>
      )}
    </div>
  );
}

function Changes({ changes }: { changes: PreviewResult["changes"] }) {
  const [all, setAll] = useState(false);
  const shown = all ? changes : changes.slice(0, 8);
  return (
    <div className="changes">
      {shown.map((c) => (
        <div key={c.path}>
          <span className="path">{c.path}</span>
          <span className="delta">
            <del>{display(c.before)}</del> → <ins>{display(c.after)}</ins>
          </span>
        </div>
      ))}
      {changes.length > 8 && (
        <button className="btn small" onClick={() => setAll((x) => !x)}>
          {all ? "Show fewer" : `Show all ${changes.length} changes`}
        </button>
      )}
    </div>
  );
}

function ImpactView({ result, showAll }: { result: PreviewResult; showAll: boolean }) {
  const { impact } = result;
  const rows = showAll ? impact.rows : impact.rows.filter((r) => r.changed);
  return (
    <>
      <div className="compare">
        <div className="stat">
          <Delta before={impact.before.need_you} after={impact.after.need_you} />
          <div className="l">need you</div>
        </div>
        <div className="stat">
          <Delta before={impact.before.quiet} after={impact.after.quiet} invert />
          <div className="l">handled quietly</div>
        </div>
        <div className="stat">
          <div className="n">{impact.changed}</div>
          <div className="l">decisions change</div>
        </div>
      </div>
      <div>
        <div className="eyebrow">Rule changes ({result.changes.length})</div>
        {result.changes.length ? <Changes changes={result.changes} /> : <span className="muted">No field changes.</span>}
      </div>
      <div>
        <div className="eyebrow">Before → after · peak rung per contact</div>
        <div className="diff-table">
          {rows.length ? rows.map((r) => <DiffRow key={r.contact_id} row={r} />) : <span className="muted">No decision changes on this replay.</span>}
        </div>
      </div>
    </>
  );
}

function History({ history, onRevert, busy }: { history: TwistEntry[]; onRevert: (e: TwistEntry) => void; busy: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className="twist-section" aria-label="Twist history">
      <div className="section-head">
        <span className="eyebrow">Twist history</span>
        <span className="muted small">Edits to config/rules.yaml appear here too</span>
      </div>
      {history.length === 0 ? (
        <div className="empty small">No twists yet. Pick a preset, or edit config/rules.yaml and save.</div>
      ) : (
        <div className="history-list">
          {history.map((e) => {
            const imp = e.impact;
            return (
              <div className="history-item" key={e.id}>
                <div className="history-row">
                  <span className="tid">{e.id}</span>
                  <span className={cls("source", `src-${e.source}`)}>{e.source}</span>
                  <span className="history-text">
                    <strong>{e.title}</strong>
                    {e.note && <span className="muted"> · {e.note}</span>}
                    <div className="muted small">
                      {new Date(e.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · rules v{e.rules_version} ·{" "}
                      {e.changes.length} field{e.changes.length === 1 ? "" : "s"}
                      {imp ? ` · need you ${imp.before.need_you} → ${imp.after.need_you} · ${imp.changed} changed` : " · computing impact…"}
                    </div>
                  </span>
                </div>
                <div className="history-actions">
                  <button className="why-toggle" aria-expanded={open === e.id} onClick={() => setOpen(open === e.id ? null : e.id)}>
                    Details <Icon name="chevronDown" size={14} />
                  </button>
                  <button className="btn small" disabled={busy || e.source === "revert"} onClick={() => onRevert(e)}>
                    <Icon name="undo" size={16} /> Revert
                  </button>
                </div>
                {open === e.id && (
                  <div className="history-detail">
                    <Changes changes={e.changes} />
                    {imp && (
                      <div className="diff-table">
                        {imp.rows.map((r) => (
                          <DiffRow key={r.contact_id} row={r} />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function TwistConsole({
  config,
  snap,
  history,
  toast,
}: {
  config: Config;
  snap: Snapshot;
  history: TwistEntry[];
  toast: (text: string, kind?: "error" | "ok") => void;
}) {
  const base = config.rules;
  const [draft, setDraft] = useState<RulesData>(base);
  const [yaml, setYaml] = useState<string | null>(null);
  const [yamlBase, setYamlBase] = useState("");
  const [tab, setTab] = useState<Tab>("thresholds");
  const [preset, setPreset] = useState<Preset | null>(null);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [scenario, setScenario] = useState(snap.scenario.id);
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    setDraft(base);
    setYaml(null);
    setResult(null);
    setPreset(null);
  }, [config.version]);

  useEffect(() => {
    setScenario(snap.scenario.id);
  }, [snap.scenario.id]);

  useEffect(() => {
    if (tab !== "yaml") return;
    api.rulesText().then((r) => {
      setYamlBase(r.text);
      setYaml((y) => y ?? r.text);
    });
  }, [tab, config.version]);

  const yamlDirty = yaml !== null && yaml !== yamlBase && yamlBase !== "";
  const formDirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(base), [draft, base]);
  const dirty = yamlDirty || formDirty;
  const payload: TwistPayload | null = dirty ? (yamlDirty ? { yaml: yaml! } : { rules: draft }) : null;
  const debounced = useDebounced(JSON.stringify({ payload, scenario }), 450);

  useEffect(() => {
    const { payload: p, scenario: s } = JSON.parse(debounced) as { payload: TwistPayload | null; scenario: string };
    if (!p) {
      setResult(null);
      setError(null);
      return;
    }
    let live = true;
    setLoading(true);
    api
      .preview({ ...p, scenario: s })
      .then((r) => {
        if (!live) return;
        setResult(r);
        setError(null);
      })
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [debounced]);

  const set = (path: PathKey, value: unknown) => {
    setDraft((d) => setIn(d, path, value));
    setPreset(null);
  };

  const pickPreset = async (p: Preset) => {
    try {
      const r = await api.preview({ ops: p.ops, scenario });
      setDraft(r.candidate);
      setYaml(null);
      setPreset(p);
      setTitle(p.title);
      setNote(p.description);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const discard = () => {
    setDraft(base);
    setYaml(yamlBase || null);
    setPreset(null);
    setTitle("");
    setNote("");
  };

  const apply = async () => {
    if (!payload) return;
    setBusy(true);
    try {
      const entry = await api.apply({
        ...payload,
        scenario,
        title: title.trim() || preset?.title || "Live twist",
        note: note.trim(),
        source: preset ? "preset" : "ui",
      });
      toast(`${entry.id} applied · rules v${entry.rules_version}`, "ok");
      setTitle("");
      setNote("");
      setPreset(null);
      setYaml(null);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const revert = async (e: TwistEntry) => {
    setBusy(true);
    try {
      const r = await api.revert(e.id);
      toast(`Reverted ${e.id} · rules v${r.rules_version}`, "ok");
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const ctx = { draft, base, set };

  return (
    <div className="twist">
      <section className="twist-section" aria-label="Twist presets">
        <span className="eyebrow">Presets</span>
        <div className="presets" role="group">
          {config.presets.map((p) => (
            <button key={p.id} className="preset" aria-pressed={preset?.id === p.id} onClick={() => pickPreset(p)}>
              <strong>{p.title}</strong>
              <span>{p.description}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="twist-section" aria-label="Rule editor">
        <div className="segmented tabs" role="tablist">
          {TABS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} aria-pressed={tab === k} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </div>
        {tab === "thresholds" && <ThresholdsEditor {...ctx} />}
        {tab === "ladder" && <LadderEditor {...ctx} />}
        {tab === "zones" && <ZonesEditor c={ctx} />}
        {tab === "schedule" && <ScheduleEditor {...ctx} />}
        {tab === "yaml" && (
          <div className="editor-body">
            <p className="muted small">
              The same file the server watches. Edits are validated before anything changes{formDirty ? "; they replace the form edits." : "."}
            </p>
            <textarea className="yaml" spellCheck={false} value={yaml ?? ""} onChange={(e) => setYaml(e.target.value)} aria-label="rules.yaml" />
          </div>
        )}
      </section>

      <section className="twist-section impact" aria-label="Impact preview">
        <div className="section-head">
          <span className="eyebrow">Impact on replay</span>
          {loading && <span className="spinner" aria-label="Running replay" />}
          <label className="scenario-select inline">
            <select value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Replay scenario">
              {config.scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
            <Icon name="chevronDown" size={14} />
          </label>
        </div>
        {!dirty && <p className="muted small">Pick a preset or change a value. Quietwater replays the scenario with the old and new rules and shows every decision that moves.</p>}
        {dirty && error && (
          <div className="error-box" role="alert">
            <strong>Not valid yet.</strong> {error}
          </div>
        )}
        {dirty && result && !error && <ImpactView result={result} showAll={showAll} />}
        {dirty && result && !error && (
          <label className="check-label">
            <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Show unchanged contacts
          </label>
        )}
        <div className="apply-bar">
          <input className="field-input" placeholder="Twist name" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Twist name" />
          <input className="field-input" placeholder="Note for the audit log" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Twist note" />
          <div className="apply-actions">
            <button className="btn" onClick={discard} disabled={!dirty || busy}>
              Discard
            </button>
            <button className="btn primary" onClick={apply} disabled={!dirty || busy || !!error || loading}>
              <Icon name="check" size={18} /> Apply live
            </button>
          </div>
        </div>
      </section>

      <History history={history} onRevert={revert} busy={busy} />
    </div>
  );
}

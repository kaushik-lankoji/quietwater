import type { ReactNode } from "react";
import { cls } from "../format";
import { RUNGS, type Harbor, type RegistryEntry, type Rung, type RulesData, type Shape, type Zone } from "../types";
import { HarborMap } from "./HarborMap";
import { Icon } from "./Icon";

export type PathKey = (string | number)[];
export type Setter = (path: PathKey, value: unknown) => void;

export function getIn(obj: unknown, path: PathKey): unknown {
  let cur: unknown = obj;
  for (const k of path) {
    if (cur === null || cur === undefined) return undefined;
    cur = (cur as Record<string | number, unknown>)[k];
  }
  return cur;
}

export function setIn<T>(obj: T, path: PathKey, value: unknown): T {
  const out = structuredClone(obj);
  let cur = out as Record<string | number, unknown>;
  path.slice(0, -1).forEach((k) => {
    cur = cur[k] as Record<string | number, unknown>;
  });
  cur[path[path.length - 1]] = value;
  return out;
}

interface Ctx {
  draft: RulesData;
  base: RulesData;
  set: Setter;
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

function Slider({ c, path, label, min, max, step, fmt, hint }: {
  c: Ctx;
  path: PathKey;
  label: string;
  min: number;
  max: number;
  step: number;
  fmt?: (v: number) => string;
  hint?: string;
}) {
  const v = Number(getIn(c.draft, path));
  const dirty = !same(v, getIn(c.base, path));
  return (
    <div className={cls("field", dirty && "dirty")}>
      <label>
        {label}
        <span className="val">{fmt ? fmt(v) : v}</span>
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={v}
        aria-label={label}
        onChange={(e) => c.set(path, Number(e.target.value))}
      />
      {hint && <small>{hint}</small>}
    </div>
  );
}

function NumberField({ c, path, label, step = 1, min = 0, hint, suffix }: {
  c: Ctx;
  path: PathKey;
  label: string;
  step?: number;
  min?: number;
  hint?: string;
  suffix?: string;
}) {
  const v = getIn(c.draft, path) as number;
  const dirty = !same(v, getIn(c.base, path));
  return (
    <div className={cls("field", dirty && "dirty")}>
      <label>
        {label}
        {suffix && <span className="muted">{suffix}</span>}
      </label>
      <input
        className="num"
        type="number"
        step={step}
        min={min}
        value={Number.isFinite(v) ? v : ""}
        aria-label={label}
        onChange={(e) => c.set(path, e.target.value === "" ? 0 : Number(e.target.value))}
      />
      {hint && <small>{hint}</small>}
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="field-group">
      <h3>{title}</h3>
      <div className="fields">{children}</div>
    </div>
  );
}

const pctFmt = (v: number) => `${Math.round(v * 100)}%`;

export function ThresholdsEditor(c: Ctx) {
  const kinds = Object.keys(c.draft.consequence.by_kind);
  const humanFrom = c.draft.human_required_from;
  return (
    <div className="editor-body">
      <Group title="Classifier confidence">
        <Slider c={c} path={["thresholds", "classify_confidence"]} label="Trust a label at" min={0.3} max={0.99} step={0.01} fmt={pctFmt} hint="Below this, a contact is treated as unknown." />
        <Slider c={c} path={["thresholds", "non_vehicle_confidence"]} label="Dismiss fish/debris at" min={0.3} max={0.99} step={0.01} fmt={pctFmt} />
        <Slider c={c} path={["thresholds", "improvised_confidence"]} label="Improvised-device signature at" min={0.3} max={0.99} step={0.01} fmt={pctFmt} />
      </Group>
      <Group title="Consequence bands (distance to an active asset)">
        <NumberField c={c} path={["consequence", "default", "high_m"]} label="Default · high within" suffix="m" step={10} />
        <NumberField c={c} path={["consequence", "default", "medium_m"]} label="Default · medium within" suffix="m" step={10} />
        {kinds.flatMap((k) => [
          <NumberField key={`${k}h`} c={c} path={["consequence", "by_kind", k, "high_m"]} label={`${k.replace("_", " ")} · high within`} suffix="m" step={10} />,
          <NumberField key={`${k}m`} c={c} path={["consequence", "by_kind", k, "medium_m"]} label={`${k.replace("_", " ")} · medium within`} suffix="m" step={10} />,
        ])}
      </Group>
      <Group title="Behavior">
        <NumberField c={c} path={["approach", "radius_m"]} label="Approach radius" suffix="m" step={10} />
        <NumberField c={c} path={["approach", "min_speed_mps"]} label="Approach min speed" suffix="m/s" step={0.1} />
        <NumberField c={c} path={["approach", "cone_deg"]} label="Approach cone" suffix="°" step={5} />
        <NumberField c={c} path={["traffic_radius_m"]} label="Traffic radius for Slow" suffix="m" step={25} />
        <NumberField c={c} path={["hail", "timeout_s"]} label="Hail answer window" suffix="s" />
        <NumberField c={c} path={["evasion", "turn_deg"]} label="Evasion: turn after hail" suffix="°" step={10} />
      </Group>
      <Group title="Second-look loop">
        <NumberField c={c} path={["loop", "max_second_looks"]} label="Max second looks" hint="Then escalate one rung. Never loops forever." />
        <NumberField c={c} path={["loop", "interval_s"]} label="Look interval" suffix="s" />
        <NumberField c={c} path={["loop", "escalate_by"]} label="Escalate by" suffix="rungs" min={1} />
      </Group>
      <div className="field-group">
        <h3>Who decides</h3>
        <div className={cls("field", !same(humanFrom, c.base.human_required_from) && "dirty")}>
          <label>A person approves from</label>
          <div className="chips" role="group" aria-label="Human approval from rung">
            {RUNGS.slice(0, 5).map((r) => (
              <button key={r} className={cls("rung-toggle", r)} aria-pressed={r === humanFrom} onClick={() => c.set(["human_required_from"], r)}>
                {r}
              </button>
            ))}
            <span className="muted" style={{ alignSelf: "center", fontSize: 12.5 }}>
              Hold (R4) and Hand off (R5) always need a person.
            </span>
          </div>
        </div>
        <div className="fields">
          <NumberField c={c} path={["windows_s", "urgent"]} label="Urgent window" suffix="s" step={30} />
          <NumberField c={c} path={["windows_s", "hold_handoff"]} label="Hold + hand-off window" suffix="s" step={60} />
          <NumberField c={c} path={["alert_budget", "capacity"]} label="Attention budget" suffix="pts" />
          <NumberField c={c} path={["alert_budget", "keep_watching_snooze_s"]} label="Keep watching for" suffix="s" step={10} />
        </div>
      </div>
    </div>
  );
}

const LADDER_LABELS: Record<string, [string, string]> = {
  non_vehicle: ["Fish or debris", "S0 · confident non-vehicle"],
  identity_ok_noncritical: ["Checks out · normal zone", "S3 · registered or answered"],
  identity_ok_critical: ["Checks out · critical zone", "S3 · plus an informational notice"],
  awaiting_hail: ["Hail pending", "Cap while the hail has time to be answered"],
  threat: ["Improvised, hostile or closing", "S4 · behavior and consequence"],
  evasive: ["Evades investigation", "S5"],
  military: ["Military-grade, confident", "S5"],
  unknown_low: ["Unknown · low consequence", "S5 · second-look loop"],
  unknown_medium_quiet: ["Unknown · medium, no traffic", "S5"],
  unknown_medium_traffic: ["Unknown · medium, traffic near", "S5"],
  unknown_high: ["Unknown · high consequence", "S5"],
  possible: ["Possible lost vehicle", "Quiet Tuesday"],
  possible_exhausted: ["Possible, re-scans used up", "Quiet Tuesday"],
  confirmed: ["Confirmed lost vehicle", "Quiet Tuesday"],
  confirmed_traffic: ["Confirmed · traffic near", "Quiet Tuesday"],
  confirmed_hazard: ["Confirmed · near an operation", "Quiet Tuesday"],
};

function LadderRows({ c, root }: { c: Ctx; root: PathKey }) {
  const table = getIn(c.draft, root) as Record<string, Rung[]>;
  const baseTable = getIn(c.base, root) as Record<string, Rung[]>;
  return (
    <>
      {Object.keys(table).map((key) => {
        const rungs = table[key];
        const dirty = !same(rungs, baseTable?.[key]);
        const [label, hint] = LADDER_LABELS[key] ?? [key, ""];
        return (
          <tr key={key} className={cls(dirty && "dirty")}>
            <td>
              {label}
              <div className="muted" style={{ fontSize: 12, fontWeight: 500 }}>
                {hint}
              </div>
            </td>
            <td>
              <div className="chips">
                {RUNGS.map((r) => {
                  const on = rungs.includes(r);
                  return (
                    <button
                      key={r}
                      className={cls("rung-toggle", r)}
                      aria-pressed={on}
                      aria-label={`${label} ${r}`}
                      onClick={() => {
                        const next = on ? rungs.filter((x) => x !== r) : [...rungs, r].sort();
                        if (next.length) c.set([...root, key], next);
                      }}
                    >
                      {r}
                    </button>
                  );
                })}
              </div>
            </td>
          </tr>
        );
      })}
    </>
  );
}

export function LadderEditor(c: Ctx) {
  return (
    <div className="editor-body">
      <div className="field-group">
        <h3>Situation → rungs (harbor watch)</h3>
        <table className="ladder-table">
          <tbody>
            <LadderRows c={c} root={["ladder"]} />
          </tbody>
        </table>
      </div>
      <div className="field-group">
        <h3>Situation → rungs (Quiet Tuesday recovery)</h3>
        <table className="ladder-table">
          <tbody>
            <LadderRows c={c} root={["recovery", "ladder"]} />
          </tbody>
        </table>
      </div>
      {(["security", "recovery"] as const).map((mode) => (
        <div className="field-group" key={mode}>
          <h3>Rung wording · {c.draft.modes[mode].title}</h3>
          <div className="fields">
            {RUNGS.map((r) => {
              const path = ["modes", mode, "rungs", r];
              const v = getIn(c.draft, path) as { name: string; action: string };
              const dirty = !same(v, getIn(c.base, path));
              return (
                <div key={r} className={cls("field", dirty && "dirty")}>
                  <label>
                    {r}
                    <span className="muted">{"{asset} {operation} {vessels} {target}"}</span>
                  </label>
                  <input className="text-input" value={v.name} aria-label={`${r} name`} onChange={(e) => c.set([...path, "name"], e.target.value)} />
                  <input className="text-input" value={v.action} aria-label={`${r} action`} onChange={(e) => c.set([...path, "action"], e.target.value)} />
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function ShapeFields({ c, path, shape }: { c: Ctx; path: PathKey; shape: Shape }) {
  const keys = shape.type === "rect" ? ["x", "y", "w", "h"] : shape.type === "circle" ? ["x", "y", "r"] : ["width"];
  return (
    <div className="mini-fields">
      {keys.map((k) => (
        <label key={k}>
          {k}
          <input
            className="num"
            type="number"
            step={10}
            value={(shape as unknown as Record<string, number>)[k] ?? 0}
            onChange={(e) => c.set([...path, "shape", k], Number(e.target.value))}
          />
        </label>
      ))}
      {shape.type === "line" && <span className="muted" style={{ fontSize: 12, alignSelf: "end" }}>Edit points in Raw YAML</span>}
    </div>
  );
}

export function ZonesEditor({ c, harbor }: { c: Ctx; harbor: Harbor }) {
  const changed = new Set<string>();
  c.draft.zones.forEach((z) => {
    const b = c.base.zones.find((x) => x.id === z.id);
    if (!same(z, b)) changed.add(z.id);
  });
  c.draft.assets.forEach((a) => {
    const b = c.base.assets.find((x) => x.id === a.id);
    if (!same(a, b)) changed.add(a.id);
  });
  const addZone = () => {
    const id = `zone_${c.draft.zones.length + 1}`;
    const zone: Zone = { id, name: "New zone", critical: true, shape: { type: "rect", x: 1200, y: 900, w: 200, h: 150 } };
    c.set(["zones"], [zone, ...c.draft.zones]);
  };
  return (
    <div className="editor-body">
      <HarborMap harbor={harbor} rules={c.draft} compact highlight={changed} />
      <div className="field-group">
        <h3>Assets (consequence)</h3>
        {c.draft.assets.map((a, i) => (
          <div key={a.id} className={cls("item-card", changed.has(a.id) && "dirty")}>
            <div className="item-card-head">
              <strong>{a.name}</strong>
              <span className="muted mono" style={{ fontSize: 12 }}>
                {a.kind}
              </span>
              <span className="spacer" />
              <button className="chip-toggle" aria-pressed={a.active} onClick={() => c.set(["assets", i, "active"], !a.active)}>
                {a.active ? "Active" : "Inactive"}
              </button>
              <button className="btn ghost icon-only small" aria-label={`Remove ${a.name}`} onClick={() => c.set(["assets"], c.draft.assets.filter((x) => x.id !== a.id))}>
                <Icon name="close" size={15} />
              </button>
            </div>
            <div className="mini-fields" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <label>
                Name
                <input className="text-input" value={a.name} onChange={(e) => c.set(["assets", i, "name"], e.target.value)} />
              </label>
              <label>
                Operation to hold
                <input className="text-input" value={a.operation} onChange={(e) => c.set(["assets", i, "operation"], e.target.value)} />
              </label>
            </div>
            <ShapeFields c={c} path={["assets", i]} shape={a.shape} />
          </div>
        ))}
      </div>
      <div className="field-group">
        <div style={{ display: "flex", alignItems: "center" }}>
          <h3 style={{ flex: 1 }}>Zones (authorization)</h3>
          <button className="btn small" onClick={addZone}>
            + Add zone
          </button>
        </div>
        {c.draft.zones.map((z, i) => (
          <div key={z.id} className={cls("item-card", changed.has(z.id) && "dirty")}>
            <div className="item-card-head">
              <input className="text-input" style={{ maxWidth: 260 }} value={z.name} aria-label="Zone name" onChange={(e) => c.set(["zones", i, "name"], e.target.value)} />
              <span className="muted mono" style={{ fontSize: 12 }}>
                {z.id}
              </span>
              <span className="spacer" />
              <button className="chip-toggle" aria-pressed={z.critical} onClick={() => c.set(["zones", i, "critical"], !z.critical)}>
                {z.critical ? "Critical" : "Normal"}
              </button>
              <button className="btn ghost icon-only small" aria-label={`Remove ${z.name}`} onClick={() => c.set(["zones"], c.draft.zones.filter((x) => x.id !== z.id))}>
                <Icon name="close" size={15} />
              </button>
            </div>
            <ShapeFields c={c} path={["zones", i]} shape={z.shape} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScheduleEditor(c: Ctx) {
  const zones = c.draft.zones.map((z) => z.id);
  const types = Object.keys(c.draft.classes as Record<string, string>).filter(
    (k) => !["non_vehicle", "unknown", "improvised"].includes((c.draft.classes as Record<string, string>)[k]),
  );
  const add = () => {
    const entry: RegistryEntry = {
      id: `NEW-${c.draft.registry.length + 1}`,
      operator: "New operator",
      vehicle_type: "research_auv",
      size_m: 1.5,
      signature: "new-signature",
      authorized_zones: [zones.find((z) => z === "research_box") ?? zones[0]],
      schedule: [{ start: "09:00", end: "17:00" }],
    };
    c.set(["registry"], [...c.draft.registry, entry]);
  };
  return (
    <div className="editor-body">
      <div style={{ display: "flex", alignItems: "center" }}>
        <p className="muted" style={{ margin: 0, flex: 1 }}>
          A vehicle passes S1 only when it is registered, inside one of its zones, and inside a window.
        </p>
        <button className="btn small" onClick={add}>
          + Add vehicle
        </button>
      </div>
      {c.draft.registry.map((r, i) => {
        const b = c.base.registry.find((x) => x.id === r.id);
        const dirty = !same(r, b);
        return (
          <div key={i} className={cls("item-card", dirty && "dirty")}>
            <div className="item-card-head">
              {b ? (
                <strong className="mono">{r.id}</strong>
              ) : (
                <input className="text-input mono" style={{ maxWidth: 200 }} value={r.id} aria-label="Vehicle ID" onChange={(e) => c.set(["registry", i, "id"], e.target.value)} />
              )}
              <span className="muted">{r.operator}</span>
              <span className="spacer" />
              {c.draft.recovery.lost_vehicle_id === r.id && <span className="status-pill watching">lost on Quiet Tuesday</span>}
              <button
                className="btn ghost icon-only small"
                aria-label={`Remove ${r.id}`}
                onClick={() => c.set(["registry"], c.draft.registry.filter((_, j) => j !== i))}
              >
                <Icon name="close" size={15} />
              </button>
            </div>
            <div className="mini-fields" style={{ gridTemplateColumns: "1.4fr 1fr 0.6fr 1fr" }}>
              <label>
                Operator
                <input className="text-input" value={r.operator} onChange={(e) => c.set(["registry", i, "operator"], e.target.value)} />
              </label>
              <label>
                Type
                <select className="select" value={r.vehicle_type} onChange={(e) => c.set(["registry", i, "vehicle_type"], e.target.value)}>
                  {types.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label>
                Size m
                <input className="num" type="number" step={0.1} value={r.size_m} onChange={(e) => c.set(["registry", i, "size_m"], Number(e.target.value))} />
              </label>
              <label>
                Signature
                <input className="text-input mono" value={r.signature} onChange={(e) => c.set(["registry", i, "signature"], e.target.value)} />
              </label>
            </div>
            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>
                Authorized zones
              </div>
              <div className="chips">
                {zones.map((z) => {
                  const on = r.authorized_zones.includes(z);
                  return (
                    <button
                      key={z}
                      className="chip-toggle"
                      aria-pressed={on}
                      onClick={() =>
                        c.set(["registry", i, "authorized_zones"], on ? r.authorized_zones.filter((x) => x !== z) : [...r.authorized_zones, z])
                      }
                    >
                      {z}
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>
                Schedule
              </div>
              <div style={{ display: "grid", gap: 6 }}>
                {r.schedule.map((w, j) => (
                  <div className="window-row" key={j}>
                    <input type="time" value={w.start} aria-label="Start" onChange={(e) => c.set(["registry", i, "schedule", j, "start"], e.target.value)} />
                    <span className="muted">to</span>
                    <input type="time" value={w.end} aria-label="End" onChange={(e) => c.set(["registry", i, "schedule", j, "end"], e.target.value)} />
                    <button className="btn ghost icon-only small" aria-label="Remove window" onClick={() => c.set(["registry", i, "schedule"], r.schedule.filter((_, k) => k !== j))}>
                      <Icon name="close" size={15} />
                    </button>
                  </div>
                ))}
                <div>
                  <button className="btn small" onClick={() => c.set(["registry", i, "schedule"], [...r.schedule, { start: "12:00", end: "14:00" }])}>
                    + Window
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

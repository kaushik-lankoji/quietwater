export type Rung = "R0" | "R1" | "R2" | "R3" | "R4" | "R5";
export const RUNGS: Rung[] = ["R0", "R1", "R2", "R3", "R4", "R5"];
export type Mode = "security" | "recovery";
export type Urgency = "routine" | "elevated" | "urgent";
export type Point = [number, number];

export interface Check {
  key: string;
  label: string;
  ruled_out: boolean | null;
  detail: string;
}

export interface AssetRef {
  id: string;
  name: string;
  kind: string;
  operation: string;
  distance_m: number;
}

export interface Drift {
  heading: number;
  speed_kn: number;
  horizon_s: number;
  projected: Point;
  eta_critical: { zone: string; seconds: number } | null;
  nearest_hazard_at_horizon: { name: string; distance_m: number } | null;
}

export interface Decision {
  contact_id: string;
  t: number;
  clock: string;
  track: Mode;
  outcome: string;
  rungs: Rung[];
  rung: Rung;
  rung_names: string[];
  path: string[];
  reason: string;
  checks: Check[];
  ruled_out: string[];
  urgency: Urgency;
  window_s: number | null;
  requires_human: boolean;
  recommendation: string;
  why_higher: string;
  why_lower: string;
  notice: string | null;
  label: string;
  label_text: string;
  confidence: number;
  category: string;
  consequence: "low" | "medium" | "high";
  nearest_asset: AssetRef | null;
  focus_asset: AssetRef | null;
  position: Point;
  heading: number;
  speed_kn: number;
  size_m: number;
  zone: string;
  registered: boolean;
  registry_id: string | null;
  hail: string;
  look: number;
  max_looks: number;
  traffic: string[];
  drift: Drift | null;
}

export interface Contact {
  id: string;
  x: number;
  y: number;
  heading: number;
  speed_kn: number;
  size_m: number;
  label: string;
  label_text: string;
  confidence: number;
  rung: Rung;
  rungs: Rung[];
  rung_names: string[];
  urgency: Urgency;
  requires_human: boolean;
  outcome: string;
  zone: string;
  registry_id: string | null;
  track: Mode;
  reason: string;
  trail: Point[];
}

export interface Receipt {
  id: string;
  seq: number;
  contact_id: string;
  t: number;
  clock: string;
  automated: boolean;
  rules_version: number;
  mode: Mode;
  decision: Decision;
}

export interface Step {
  clock: string;
  rungs: string;
  reason: string;
  automated: boolean;
}

export type ItemStatus = "pending" | "watching" | "approved" | "rejected" | "stood_down";

export interface HandoffItem {
  id: string;
  contact_id: string;
  created_t: number;
  created_clock: string;
  deadline_t: number;
  decision: Decision;
  status: ItemStatus;
  overdue: boolean;
  contact_lost: boolean;
  snooze_until: number | null;
  resolved_t: number | null;
  resolved_clock: string | null;
  actor: string | null;
  note: string | null;
  draft: { to: string; subject: string; body: string } | null;
  draft_status: "drafted" | "sent" | null;
  steps: Step[];
  remaining_s: number;
  window_s: number | null;
}

export interface Budget {
  seen: number;
  active: number;
  quiet: number;
  need_you: number;
  watching: number;
  resolved: number;
  load: number;
  capacity: number;
  over: boolean;
  bang: number;
  rung_counts: Record<Rung, number>;
  automated_actions: number;
  trace: number[];
}

export interface ScenarioRef {
  id: string;
  title: string;
  description: string;
  duration_s: number;
  seed: number;
}

export interface Snapshot {
  run: number;
  t: number;
  clock: string;
  running: boolean;
  speed: number;
  scenario: ScenarioRef;
  mode: Mode;
  rules: { version: number; error: string | null };
  contacts: Contact[];
  items: HandoffItem[];
  budget: Budget;
  receipts: Receipt[];
}

export interface FieldChange {
  path: string;
  before: unknown;
  after: unknown;
}

export interface Totals {
  contacts: number;
  quiet: number;
  need_you: number;
}

export interface CompactDecision {
  rungs: Rung[];
  rung: Rung;
  rung_names: string[];
  outcome: string;
  reason: string;
  requires_human: boolean;
  urgency: Urgency;
  path: string[];
  label_text: string;
}

export interface ImpactRow {
  contact_id: string;
  label: string;
  before: CompactDecision | null;
  after: CompactDecision | null;
  changed: boolean;
  direction: "up" | "down" | "same";
  first_human_t: { before: number | null; after: number | null };
}

export interface Impact {
  scenario: string;
  mode: Mode;
  seed: number;
  duration_s: number;
  before: Totals;
  after: Totals;
  changed: number;
  rows: ImpactRow[];
}

export interface TwistEntry {
  id: string;
  at: string;
  source: "ui" | "preset" | "file" | "revert";
  title: string;
  note: string;
  rules_version: number;
  clock: string;
  scenario: string;
  changes: FieldChange[];
  impact: Impact | null;
}

export interface Shape {
  type: "rect" | "circle" | "line";
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  r?: number;
  points?: Point[];
  width?: number;
}

export interface Zone {
  id: string;
  name: string;
  critical: boolean;
  shape: Shape;
}

export interface Asset {
  id: string;
  name: string;
  kind: string;
  operation: string;
  active: boolean;
  shape: Shape;
}

export interface Vessel {
  id: string;
  name: string;
  x: number;
  y: number;
}

export interface Window {
  start: string;
  end: string;
}

export interface RegistryEntry {
  id: string;
  operator: string;
  vehicle_type: string;
  size_m: number;
  signature: string;
  authorized_zones: string[];
  schedule: Window[];
}

export interface ModeText {
  title: string;
  customer: string;
  handoff_target: string;
  rungs: Record<Rung, { name: string; action: string }>;
}

export interface RulesData {
  harbor: { name: string; origin: { lat: number; lon: number }; clock_start: string };
  thresholds: Record<string, number>;
  consequence: { default: Band; by_kind: Record<string, Band> };
  approach: { radius_m: number; cone_deg: number; min_speed_mps: number };
  hail: { timeout_s: number };
  traffic_radius_m: number;
  loop: { max_second_looks: number; interval_s: number; escalate_by: number };
  ladder: Record<string, Rung[]>;
  human_required_from: Rung;
  windows_s: { urgent: number; hold_handoff: number; default: number };
  alert_budget: { capacity: number; weights: Record<Rung, number>; keep_watching_snooze_s: number };
  zones: Zone[];
  assets: Asset[];
  traffic: Vessel[];
  registry: RegistryEntry[];
  recovery: { lost_vehicle_id: string; confirm_confidence: number; ladder: Record<string, Rung[]> } & Record<string, unknown>;
  modes: Record<Mode, ModeText>;
  [key: string]: unknown;
}

export interface Band {
  high_m: number;
  medium_m: number;
}

export interface Harbor {
  bounds: { w: number; h: number };
  land: Point[][];
  piers: { name: string; x: number; y: number; w: number; h: number }[];
  labels: { text: string; x: number; y: number; rotate?: number }[];
}

export interface ScenarioInfo {
  id: string;
  title: string;
  description: string;
  mode: Mode;
  duration_s: number;
  contacts: number;
}

export interface Preset {
  id: string;
  title: string;
  description: string;
  ops: { op?: string; path: string; value?: unknown }[];
}

export interface Config {
  harbor: Harbor;
  rules: RulesData;
  version: number;
  error: string | null;
  scenarios: ScenarioInfo[];
  presets: Preset[];
}

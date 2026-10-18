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
  scan_label?: "debris" | "marine_life" | "known_vehicle" | "unknown";
  trend?: "new" | "closing" | "leaving" | "loitering" | "steady";
  closing_mps?: number;
  cpa?: { asset: AssetRef; distance_m: number; in_s: number; level: "low" | "medium" | "high" } | null;
  consequence_basis?: "distance" | "cpa";
  ambiguous?: boolean;
  ai_raised_tier?: number;
  ai_reason?: string | null;
  advisor?: AdvisorReceipt | null;
}

export interface AdvisorReceipt {
  source: "rule" | "llm" | "rule_fallback" | "fail_safe";
  inputs: Record<string, unknown>;
  suggestion: { suggested_tier_raise: number; second_look: boolean; reason: string; confidence: number };
  applied: boolean;
  raised_rungs: number;
  clamped: boolean;
  error: string | null;
  reason: string;
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
  config_hash?: string;
  mode: Mode;
  decision: Decision;
  kind?: "handoff";
  transition?: { item: string; action: string; from: ItemStatus; to: ItemStatus; actor: string; label: string };
}

export interface Step {
  clock: string;
  rungs: string;
  reason: string;
  automated: boolean;
}

export type ItemStatus =
  | "pending"
  | "watching"
  | "expired"
  | "hold_requesting"
  | "hold_active"
  | "hold_failed"
  | "notice_review"
  | "notice_sent"
  | "dismissed"
  | "resolved"
  | "lifted"
  | "stood_down";

export type HandoffAction =
  | "approve"
  | "retry"
  | "review"
  | "edit"
  | "cancel"
  | "send"
  | "dismiss"
  | "undo"
  | "watch"
  | "escalate"
  | "lift"
  | "resolve"
  | "extend";

export interface PlanStep {
  kind: "hold" | "notice";
  rung: Rung;
  title: string;
  detail: string;
  asset?: string;
  operation?: string;
  on: "approve" | "separate";
}

export type HoldScope = "operation" | "area";

export interface HoldTarget {
  asset: string;
  operation: string;
}

export interface HoldOption {
  scope: HoldScope;
  title: string;
  action: string;
  summary: string;
  detail: string;
  targets: HoldTarget[];
}

export interface HoldOptions {
  options: HoldOption[];
  recommended: HoldScope;
  reason: string;
  radius_m: number;
}

export interface Hold {
  scope: HoldScope;
  targets: HoldTarget[];
  recommended: HoldScope;
  radius_m?: number;
  status: "requesting" | "active" | "failed" | "lifted";
  request_id: string;
  asset: string;
  operation: string;
  title: string;
  requested_clock: string;
  confirmed_clock?: string;
  lifted_clock?: string;
  until_t: number | null;
  time_up?: boolean;
}

export interface ItemEvent {
  action: string;
  from: ItemStatus | null;
  to: ItemStatus;
  actor: string;
  clock: string;
  t: number;
}

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
  draft: { to: string; subject: string; body: string; language?: string } | null;
  draft_status: "drafted" | "sent" | null;
  draft_edited: boolean;
  steps: Step[];
  remaining_s: number;
  window_s: number | null;
  plan: PlanStep[];
  hold: Hold | null;
  hold_options: HoldOptions | null;
  review_from: ItemStatus | null;
  paged: boolean;
  history: ItemEvent[];
  watch_left_s: number | null;
  hold_left_s: number | null;
  undo_left_s: number | null;
}

export interface Budget {
  seen: number;
  total?: number;
  needed_operator?: number;
  active: number;
  quiet: number;
  need_you: number;
  watching: number;
  holds?: number;
  in_progress?: number;
  notices_sent?: number;
  dismissed?: number;
  expired?: number;
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
  coverage_radius_m: number;
  traffic_level?: string | null;
}

export interface OptimizationMetrics {
  coverage_radius_m: number;
  coverage_km2: number;
  traffic_level: string;
  contacts_seen: number;
  handled_quietly: number;
  human_interruptions: number;
  officer_minutes: number;
  officer_time_saved_min: number;
  officer_capacity_value_usd: number;
  manual_triage_min_per_contact: number;
  current_operators: number;
  recommended_operators: number | null;
  response_windows_feasible: boolean;
  utilization_pct: number;
  watch_horizon_min: number;
  recommended_hold_radius_m: number | null;
  baseline_hold_radius_m: number;
  hold_radius_range_m: [number, number] | null;
  modeled_pause_operation_min: number;
  baseline_pause_operation_min: number;
  estimated_cost_usd: number;
  baseline_cost_usd: number;
  cost_savings_usd: number;
  cost_savings_pct: number;
  cost_per_km2_usd: number | null;
  savings_per_km2_usd: number | null;
  staffing_cost_usd: number;
  pause_cost_usd: number;
  ai_cost_usd: number;
  avoided_pause_cost_usd: number;
  operator_hourly_usd: number;
  paused_operation_hourly_usd: number;
  llm_calls: number;
  mean_decision_ms: number | null;
  decision_count: number;
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
  optimization: OptimizationMetrics;
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
  handoff?: { hold_s: number; undo_s: number; mock_hold_delay_s: number; area_radius_m: number;
    area_radius_candidates_m?: number[]; area_safety_buffer_m?: number };
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
  random: boolean;
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

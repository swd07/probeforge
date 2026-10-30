export interface Meta {
  model: string;
  title: string;
  neutral: string;
  scenarios: { id: string; symptom: string }[];
  buttons: { id: string; label: string }[];
  lamps: { id: string; label: string }[];
  components: ComponentInfo[];
  thermal_relays: string[];
}

export interface Panel {
  lamps: Record<string, boolean>;
  motor: string;
  line_currents: Record<string, string>;
  line_currents_a: Record<string, number>;
  power: boolean;
  time_s: number;
}

export type Bench = "star_delta" | "ats";

/** ATS bench: what a technician at the transfer switch sees (server/ats.py snapshot). */
export interface AtsPanel {
  ats: true;
  lights: Record<string, boolean>;
  display: string;
  alarms: string[];
  metering: { Normal: number[]; Emergency: number[] };
  events: { t: number; event: string; cause: string }[];
  normal_source: string;
  generator: string;
  load_powered: boolean;
  ups: { autonomy_s: number; left_s: number; draining: boolean; depleted: boolean };
  time_s: number;
  position: string;
  isolated: boolean;
  flow: number;
}

export interface AtsMeta extends Meta {
  repairs: Record<string, string[]>;
  limits: { action: string; tier: string; condition: string }[];
  ups_autonomy_s: number;
  action_s: number;
  flow: string[];
}

export interface Probe {
  kind: "V" | "R";
  a: string;
  b: string;
  value: number | string;
  net_a: string;
  net_b: string;
  term_a: string;
  term_b: string;
  step: number;
}

export interface Hypothesis {
  component: string;
  part?: string;
  failure_mode: string;
  probability: number;
  reason: string;
}

export interface ToolEvent {
  type: "tool";
  step: number;
  tool: string;
  args: Record<string, unknown>;
  verdict: "allow" | "block" | "needs_approval" | "needs_strong_approval" | "error";
  policy_reason: string;
  executed: boolean;
  result: Record<string, unknown>;
  sim_time_s: number;
  probes: Probe[];
  panel: Panel;
}

export interface ApprovalRequest {
  id: number;
  step: number;
  tool: string;
  args: Record<string, unknown>;
  policy_reason: string;
  agent_reason: string;
  // ATS bench: strong approval (second confirmation), facts stated by the policy, cited evidence steps
  strong?: boolean;
  facts?: string[];
  evidence?: { step: number; text: string }[];
}

export interface Done {
  mode: Mode;
  source: string; // the pool or scenario the fault came from
  fault: string;
  latent: boolean;
  twins: string[];
  outcome: string;
  diagnosis: Record<string, unknown> | null;
  verdict: "correct" | "justified" | "pole open" | "wrong" | "no diagnosis";
  component_ok: boolean;
  mode_ok: boolean;
  measurements: number;
  redundant: number;
  turns: number;
  tokens: number;
  cost_usd: number;
  seconds: number;
  policy_blocked: number;
  approvals: number;
  approvals_denied: number;
  recovered_text_calls: number;
  error: string | null;
  panel: Panel;
  truth_live_nets: string[];
  decisive: {
    step: number;
    reading: string;
    healthy: string | null;
    meter: boolean;
    shared_with: number;
    reason: string;
    before: number;
    after: number;
    delta: number;
  } | null;
  // ATS bench only
  bench?: Bench;
  intervention?: boolean;
  strong_approvals?: number;
  // hybrid pipeline only
  explanation?: string;
  cited_steps?: number[];
  transcription?: string;
  transcription_wrong_nets?: number;
  corrections?: { step: number; diff: string[]; explanation: string; error?: string | null; rejected?: string | null; reasons?: string[] }[];
  gave_up?: boolean;
  wiring_check?: { component: string; region: string[]; verdict: string; alternatives: number; consistent_alternatives: number } | null;
}

export interface WiringRequest {
  id: number;
  component: string;
  failure_mode: string;
  region: string[];
  reasons: string[];
  options: { fault: string; wiring: string[] }[];
}

export interface Flag {
  terminals: string[];
  reason: string;
}

export interface FlagsRequest {
  id: number;
  flags: Flag[];
}

export type FeedItem =
  | { kind: "thought"; id: string; text: string; turn: number }
  | { kind: "tool"; id: string; ev: ToolEvent }
  | { kind: "hypotheses"; id: string; step: number; top: Hypothesis | null }
  | { kind: "approval"; id: string; req: ApprovalRequest; approved?: boolean }
  | { kind: "info"; id: string; text: string }
  | { kind: "transcription"; id: string; how: string; flags: Flag[]; components: number; nets: number; accepted?: boolean }
  | { kind: "conflict"; id: string; step: number; action: string; actual: string; candidates: number }
  | { kind: "correction"; id: string; step: number; diff: string[]; explanation: string }
  | { kind: "correction_rejected"; id: string; step: number; diff: string[]; reasons: string[] }
  | { kind: "wiring"; id: string; text: string };

export type NetState = "live" | "dead" | "probed";

export interface ComponentInfo {
  id: string;
  type: string;
  label: string;
  modes: string[];
  parts: { name: string; kind: string; modes: string[] }[];
}

export interface CompareColumn {
  runner: string;
  diagnosis?: string;
  confidence?: number | null;
  verdict?: string;
  measurements?: number;
  redundant?: number;
  blocked?: number;
  approvals?: number;
  seconds?: number;
  cost_usd?: number;
  sequence?: string[];
  error?: string;
}

export interface CompareResult {
  fault: string;
  columns: Record<string, CompareColumn>;
  note: string;
}

export type Mode = "agent" | "manual" | "hybrid";

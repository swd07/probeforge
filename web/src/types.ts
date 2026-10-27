export interface Meta {
  model: string;
  title: string;
  neutral: string;
  scenarios: { id: string; symptom: string }[];
  buttons: { id: string; label: string }[];
  lamps: { id: string; label: string }[];
}

export interface Panel {
  lamps: Record<string, boolean>;
  motor: string;
  line_currents: Record<string, string>;
  line_currents_a: Record<string, number>;
  power: boolean;
  time_s: number;
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
  verdict: "allow" | "block" | "needs_approval" | "error";
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
}

export interface Done {
  fault: string;
  latent: boolean;
  twins: string[];
  outcome: string;
  diagnosis: Record<string, unknown> | null;
  verdict: "correct" | "justified" | "wrong" | "no diagnosis";
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
}

export type FeedItem =
  | { kind: "thought"; id: string; text: string; turn: number }
  | { kind: "tool"; id: string; ev: ToolEvent }
  | { kind: "hypotheses"; id: string; step: number; top: Hypothesis | null }
  | { kind: "approval"; id: string; req: ApprovalRequest; approved?: boolean }
  | { kind: "info"; id: string; text: string };

export type NetState = "live" | "dead" | "probed";

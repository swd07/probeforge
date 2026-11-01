// The session state and its reducer: every server event becomes a state change here (useSession.ts holds the
// WebSocket and the actions).
import type { ApprovalRequest, AtsTranscription, Bench, CompareResult, Done, FeedItem, FlagsRequest, Hypothesis, Mode, ModelCheck, NetState, NextStep, Panel, Probe, ToolEvent, WiringRequest } from "./types";

export type Status = "idle" | "running" | "approval" | "done" | "stopped" | "error";

export interface State {
  status: Status;
  mode: Mode;
  bench: Bench;
  engineer: string;
  saved: string;
  compare: CompareResult | null;
  compareProgress: { baseline: boolean; agentTurn: number; hybrid?: boolean } | null;
  source: string;
  model: string;
  effort: string;
  panel: Panel | null;
  feed: FeedItem[];
  hypotheses: Hypothesis[];
  previous: Record<string, number>;
  probes: Probe[];
  nets: Record<string, NetState>;
  pressed: { button: string; at: number } | null;
  approval: ApprovalRequest | null;
  flags: FlagsRequest | null;
  wiring: WiringRequest | null;
  stage: string;
  done: Done | null;
  nextStep: NextStep | null; // ATS hybrid: the planner's next step
  suggestion: NextStep | null; // ATS engineer mode: the planner's suggestion, only when asked for
  suggestions: number;
  atsTranscription: AtsTranscription | null;
  modelCheck: ModelCheck | null;
  tokens: number;
  turns: number;
  measurements: number;
  blocked: number;
  flash: number;
  error: string;
}

export const initial: State = {
  status: "idle",
  mode: "agent",
  bench: "star_delta",
  engineer: "",
  saved: "",
  compare: null,
  compareProgress: null,
  source: "",
  model: "",
  effort: "",
  panel: null,
  feed: [],
  hypotheses: [],
  previous: {},
  probes: [],
  nets: {},
  pressed: null,
  approval: null,
  flags: null,
  wiring: null,
  stage: "",
  done: null,
  nextStep: null,
  suggestion: null,
  suggestions: 0,
  atsTranscription: null,
  modelCheck: null,
  tokens: 0,
  turns: 0,
  measurements: 0,
  blocked: 0,
  flash: 0,
  error: "",
};

export interface StartOptions {
  mode: Mode;
  source: "scenario" | "random" | "clean";
  scenario?: string;
  effort: string;
  includeLatent: boolean;
  engineer?: string;
  schematic?: string; // hybrid: "saved" transcription or a "live" read
  bench?: Bench;
}

export const hypKey = (h: Hypothesis) => `${h.component}${h.part ? ":" + h.part : ""} ${h.failure_mode}`;

type Action = { type: "reset"; mode: Mode; bench: Bench } | { type: "event"; ev: any; neutral: string };

export function reducer(s: State, a: Action): State {
  if (a.type === "reset") return { ...initial, status: "running", mode: a.mode, bench: a.bench };
  const ev = a.ev;
  switch (ev.type) {
    case "session":
      return {
        ...initial,
        status: "running",
        mode: ev.mode ?? "agent",
        bench: ev.bench ?? "star_delta",
        engineer: ev.engineer ?? "",
        source: ev.source,
        model: ev.model ?? "",
        effort: ev.effort ?? "",
        panel: ev.panel,
      };
    case "turn": {
      const feed = ev.text?.trim()
        ? [...s.feed, { kind: "thought" as const, id: `t${ev.turn}`, text: ev.text.trim(), turn: ev.turn }]
        : s.feed;
      return { ...s, feed, turns: ev.turn, tokens: s.tokens + ev.prompt_tokens + ev.completion_tokens };
    }
    case "tool": {
      const t = ev as ToolEvent;
      if (t.tool === "update_hypotheses") return s; // shown through the "hypotheses" event
      const nets = { ...s.nets };
      for (const p of t.probes) {
        if (p.kind === "V" && (p.net_b === a.neutral || p.net_a === a.neutral)) {
          const net = p.net_b === a.neutral ? p.net_a : p.net_b;
          nets[net] = Number(p.value) > 20 ? "live" : "dead";
        } else {
          if (!nets[p.net_a]) nets[p.net_a] = "probed";
          if (!nets[p.net_b]) nets[p.net_b] = "probed";
        }
      }
      const probes = [...s.probes, ...t.probes.map((p) => ({ ...p, step: t.step }))];
      const pressed = t.tool === "press_button" && t.executed ? { button: String(t.result.button), at: Date.now() } : s.pressed;
      const blocked = t.verdict === "block" ? s.blocked + 1 : s.blocked;
      return {
        ...s,
        feed: [...s.feed, { kind: "tool", id: `s${t.step}`, ev: t }],
        panel: t.panel,
        nets,
        probes,
        pressed,
        blocked,
        flash: t.verdict === "block" ? Date.now() : s.flash,
        measurements: s.measurements + t.probes.length,
        nextStep: null, // the planned step was just taken; the planner sends the next one
        suggestion: null, // a suggestion holds only until the engineer's next step
      };
    }
    case "hypotheses": {
      const hyps = [...(ev.hypotheses as Hypothesis[])].sort((x, y) => y.probability - x.probability);
      const previous: Record<string, number> = {};
      for (const h of s.hypotheses) previous[hypKey(h)] = h.probability;
      return {
        ...s,
        hypotheses: hyps,
        previous,
        feed: [...s.feed, { kind: "hypotheses", id: `h${ev.step}`, step: ev.step, top: hyps[0] ?? null }],
      };
    }
    case "stage":
      return { ...s, stage: ev.text, feed: [...s.feed, { kind: "info", id: `stage${s.feed.length}`, text: ev.text }] };
    case "stage_done":
      return { ...s, stage: "" };
    case "ats_transcription":
      return {
        ...s,
        atsTranscription: ev,
        feed: [
          ...s.feed,
          {
            kind: "info",
            id: "ats_transcription",
            text: `Read: ${ev.label} (${ev.run_id}, recorded ${ev.recorded}): ${ev.reads} Muse Spark reads, ${ev.components} components, ${ev.nets} nets, ${ev.flags} flagged regions`,
          },
        ],
      };
    case "model_check":
      return {
        ...s,
        modelCheck: ev,
        feed: [
          ...s.feed,
          {
            kind: "info",
            id: "model_check",
            text: ev.ok
              ? `Model: the transcription reproduces the documented fault-free sequence (${ev.events.length} of ${ev.expected.length} events in order)`
              : `Model: the transcription does not reproduce the documented fault-free sequence (${ev.events.join(", ")}); no diagnosis on it`,
          },
        ],
      };
    case "next_step":
      return { ...s, nextStep: ev, feed: [...s.feed, { kind: "plan", id: `plan${s.feed.length}`, next: ev }] };
    case "suggestion":
      return {
        ...s,
        suggestion: ev,
        suggestions: s.suggestions + 1,
        feed: [...s.feed, { kind: "info", id: `sug${s.feed.length}`, text: `Planner suggestion shown after step ${ev.step} (shadow mode: this trace is marked assisted)` }],
      };
    case "transcription":
      return {
        ...s,
        stage: "",
        feed: [...s.feed, { kind: "transcription", id: "transcription", how: ev.how, flags: ev.flags, components: ev.components, nets: ev.nets }],
      };
    case "flags_request":
      return { ...s, status: "approval", flags: ev };
    case "flags_answer":
      return {
        ...s,
        status: "running",
        flags: null,
        feed: s.feed.map((f) => (f.kind === "transcription" ? { ...f, accepted: ev.accepted } : f)),
      };
    case "conflict":
      return {
        ...s,
        stage: "Muse Spark is checking the schematic against the readings...",
        flash: Date.now(),
        feed: [...s.feed, { kind: "conflict", id: `c${ev.step}_${s.feed.length}`, step: ev.step, action: ev.action, actual: ev.actual, candidates: ev.candidates }],
      };
    case "correction_rejected":
      return {
        ...s,
        stage: "",
        flash: Date.now(),
        feed: [...s.feed, { kind: "correction_rejected", id: `r${ev.step}_${s.feed.length}`, step: ev.step, diff: ev.diff, reasons: ev.reasons }],
      };
    case "wiring_check":
      return {
        ...s,
        feed: [
          ...s.feed,
          {
            kind: "wiring",
            id: `w${s.feed.length}`,
            text: `Wiring check for ${ev.component}: ${ev.alternatives} alternative wirings of the flagged region ${ev.region.join(", ")}, ${ev.consistent_alternatives} fit every reading: ${ev.verdict}`,
          },
        ],
      };
    case "wiring_variants":
      return {
        ...s,
        feed: [
          ...s.feed,
          {
            kind: "wiring",
            id: `v${ev.step}_${s.feed.length}`,
            text: `#${ev.step}: no candidate fit the reading on the transcribed wiring; an alternative wiring of a flagged region explains it (${ev.candidates} fault and wiring hypotheses, e.g. ${ev.faults.join(", ")}). No correction needed.`,
          },
        ],
      };
    case "wiring_request":
      return { ...s, status: "approval", wiring: ev };
    case "wiring_answer":
      return { ...s, status: "running", wiring: null };
    case "correction":
      return {
        ...s,
        stage: "",
        feed: [...s.feed, { kind: "correction", id: `k${ev.step}_${s.feed.length}`, step: ev.step, diff: ev.diff, explanation: ev.explanation }],
      };
    case "approval_request":
      return {
        ...s,
        status: "approval",
        approval: ev,
        feed: [...s.feed, { kind: "approval", id: `a${ev.id}`, req: ev }],
      };
    case "approval_answer":
      return {
        ...s,
        status: s.done ? "done" : "running", // ATS: approvals during the intervention come after the diagnosis
        approval: null,
        feed: s.feed.map((f) => (f.kind === "approval" && f.req.id === ev.id ? { ...f, approved: ev.approved } : f)),
      };
    case "done":
      return {
        ...s, status: "done", done: ev, panel: ev.panel, approval: null, flags: null, wiring: null, stage: "", nextStep: null,
        feed: ev.explanation ? [...s.feed, { kind: "explanation", id: `expl${s.feed.length}`, text: ev.explanation }] : s.feed,
      };
    case "saved":
      return { ...s, saved: ev.path };
    case "verified":
      return { ...s, panel: ev.panel, feed: [...s.feed, { kind: "info", id: `verified${s.feed.length}`, text: ev.message }] };
    case "compare_progress":
      return {
        ...s,
        compareProgress: {
          baseline: s.compareProgress?.baseline || ev.runner === "baseline",
          hybrid: s.compareProgress?.hybrid || ev.runner === "hybrid",
          agentTurn: ev.runner === "agent" ? ev.turn : s.compareProgress?.agentTurn ?? 0,
        },
      };
    case "compare":
      return { ...s, compare: ev, compareProgress: null };
    case "stopped":
      return {
        ...s,
        status: "stopped",
        approval: null,
        flags: null,
        wiring: null,
        stage: "",
        feed: [...s.feed, { kind: "info", id: `stopped${s.feed.length}`, text: "Session ended. Pick a fault and press Start for a new one." }],
      };
    case "connection_lost":
      // the server ends a session when its connection drops; a finished result stays readable
      if (s.status === "running" || s.status === "approval")
        return { ...s, status: "error", error: "Connection lost: the session ended. Pick a fault and press Start for a new one.", approval: null, flags: null, wiring: null, stage: "", nextStep: null };
      if (s.status === "done") return { ...s, error: "Connection lost: the result stays here; pick a fault and press Start for a new run." };
      return s;
    case "error":
      // after the run (compare refused, a click on an ended session): keep the state, show the message
      if (s.status === "done" || s.status === "stopped") return { ...s, error: ev.message };

      return { ...s, status: "error", error: ev.message, approval: null, flags: null, wiring: null, stage: "" };
    default:
      return s;
  }
}

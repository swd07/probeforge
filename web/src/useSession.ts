import { useCallback, useEffect, useReducer, useRef } from "react";
import type { ApprovalRequest, CompareResult, Done, FeedItem, FlagsRequest, Hypothesis, Mode, NetState, Panel, Probe, ToolEvent, WiringRequest } from "./types";

export type Status = "idle" | "running" | "approval" | "done" | "stopped" | "error";

export interface State {
  status: Status;
  mode: Mode;
  engineer: string;
  saved: string;
  compare: CompareResult | null;
  compareProgress: { baseline: boolean; agentTurn: number } | null;
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
  tokens: number;
  turns: number;
  measurements: number;
  blocked: number;
  flash: number;
  error: string;
}

const initial: State = {
  status: "idle",
  mode: "agent",
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
}

export const hypKey = (h: Hypothesis) => `${h.component}${h.part ? ":" + h.part : ""} ${h.failure_mode}`;

type Action = { type: "reset"; mode: Mode } | { type: "event"; ev: any; neutral: string };

function reducer(s: State, a: Action): State {
  if (a.type === "reset") return { ...initial, status: "running", mode: a.mode };
  const ev = a.ev;
  switch (ev.type) {
    case "session":
      return {
        ...initial,
        status: "running",
        mode: ev.mode ?? "agent",
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
        status: "running",
        approval: null,
        feed: s.feed.map((f) => (f.kind === "approval" && f.req.id === ev.id ? { ...f, approved: ev.approved } : f)),
      };
    case "done":
      return { ...s, status: "done", done: ev, panel: ev.panel, approval: null, flags: null, wiring: null, stage: "" };
    case "saved":
      return { ...s, saved: ev.path };
    case "compare_progress":
      return {
        ...s,
        compareProgress: {
          baseline: s.compareProgress?.baseline || ev.runner === "baseline",
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
    case "error":
      // after the run (compare refused, a click on an ended session): keep the state, show the message
      if (s.status === "done" || s.status === "stopped") return { ...s, error: ev.message };

      return { ...s, status: "error", error: ev.message, approval: null, flags: null, wiring: null, stage: "" };
    default:
      return s;
  }
}

export function useSession(neutral: string) {
  const [state, dispatch] = useReducer(reducer, initial);
  const ws = useRef<WebSocket | null>(null);
  const neutralRef = useRef(neutral);
  neutralRef.current = neutral;

  const connect = useCallback((): Promise<WebSocket> => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) return Promise.resolve(ws.current);
    return new Promise((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const sock = new WebSocket(`${proto}://${location.host}/ws`);
      sock.onmessage = (m) => dispatch({ type: "event", ev: JSON.parse(m.data), neutral: neutralRef.current });
      sock.onopen = () => resolve(sock);
      sock.onerror = () => reject(new Error("WebSocket failed"));
      sock.onclose = () => (ws.current = null);
      ws.current = sock;
    });
  }, []);

  useEffect(() => () => ws.current?.close(), []);

  const start = useCallback(
    async (opts: StartOptions) => {
      dispatch({ type: "reset", mode: opts.mode });
      const sock = await connect();
      // ?fault=QF1:5-6%20open picks a specific fault for reproducible demos and tests; the UI never offers it
      const fault = new URLSearchParams(location.search).get("fault") ?? undefined;
      sock.send(
        JSON.stringify({
          action: opts.mode === "manual" ? "start_manual" : opts.mode === "hybrid" ? "start_hybrid" : "start",
          source: opts.source,
          scenario: opts.scenario,
          effort: opts.effort,
          include_latent: opts.includeLatent,
          engineer: opts.engineer,
          schematic: opts.schematic,
          fault,
        }),
      );
    },
    [connect],
  );

  const tool = useCallback((name: string, args: Record<string, unknown>) => {
    ws.current?.send(JSON.stringify({ action: "tool", name, args }));
  }, []);

  const compare = useCallback(() => {
    dispatch({ type: "event", ev: { type: "compare_progress", runner: "start" }, neutral: neutralRef.current });
    ws.current?.send(JSON.stringify({ action: "compare" }));
  }, []);

  const answer = useCallback((id: number, approve: boolean) => {
    ws.current?.send(JSON.stringify({ action: "approval", id, approve }));
  }, []);

  const confirmFlags = useCallback((id: number, accept: boolean) => {
    ws.current?.send(JSON.stringify({ action: "flags", id, approve: accept }));
  }, []);

  const chooseWiring = useCallback((id: number, choice: number | null) => {
    ws.current?.send(JSON.stringify({ action: "wiring", id, choice }));
  }, []);

  const stop = useCallback(() => ws.current?.send(JSON.stringify({ action: "stop" })), []);

  return { state, start, answer, stop, tool, compare, confirmFlags, chooseWiring };
}

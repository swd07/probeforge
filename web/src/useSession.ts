import { useCallback, useEffect, useReducer, useRef } from "react";
import type { ApprovalRequest, CompareResult, Done, FeedItem, Hypothesis, Mode, NetState, Panel, Probe, ToolEvent } from "./types";

export type Status = "idle" | "running" | "approval" | "done" | "error";

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
  source: "scenario" | "random";
  scenario?: string;
  effort: string;
  includeLatent: boolean;
  engineer?: string;
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
      return { ...s, status: "done", done: ev, panel: ev.panel, approval: null };
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
    case "error":
      if (s.status === "done") return { ...s, error: ev.message }; // e.g. compare refused after the run

      return { ...s, status: "error", error: ev.message, approval: null };
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
          action: opts.mode === "manual" ? "start_manual" : "start",
          source: opts.source,
          scenario: opts.scenario,
          effort: opts.effort,
          include_latent: opts.includeLatent,
          engineer: opts.engineer,
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

  const stop = useCallback(() => ws.current?.send(JSON.stringify({ action: "stop" })), []);

  return { state, start, answer, stop, tool, compare };
}

import { useCallback, useEffect, useReducer, useRef } from "react";
import { initial, reducer } from "./sessionReducer";
import type { StartOptions } from "./sessionReducer";

export type { StartOptions, State, Status } from "./sessionReducer";
export { hypKey } from "./sessionReducer";

export function useSession(neutral: string) {
  const [state, dispatch] = useReducer(reducer, initial);
  const ws = useRef<WebSocket | null>(null);
  const neutralRef = useRef(neutral);
  neutralRef.current = neutral;

  const connecting = useRef<Promise<WebSocket> | null>(null);
  const lost = useCallback(() => dispatch({ type: "event", ev: { type: "connection_lost" }, neutral: neutralRef.current }), []);

  // one socket at a time: a second Start before the first socket opens reuses the pending connection
  const connect = useCallback((): Promise<WebSocket> => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) return Promise.resolve(ws.current);
    if (connecting.current) return connecting.current;
    connecting.current = new Promise<WebSocket>((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const sock = new WebSocket(`${proto}://${location.host}/ws`);
      sock.onmessage = (m) => dispatch({ type: "event", ev: JSON.parse(m.data), neutral: neutralRef.current });
      sock.onopen = () => {
        connecting.current = null;
        resolve(sock);
      };
      sock.onerror = () => {
        connecting.current = null;
        reject(new Error("WebSocket failed"));
      };
      // the server ends the session with the connection: say so instead of leaving the page waiting
      sock.onclose = () => {
        if (ws.current === sock) ws.current = null;
        connecting.current = null;
        lost();
      };
      ws.current = sock;
    });
    return connecting.current;
  }, [lost]);

  useEffect(() => () => ws.current?.close(), []);

  const start = useCallback(
    async (opts: StartOptions) => {
      dispatch({ type: "reset", mode: opts.mode, bench: opts.bench ?? "star_delta" });
      let token: string;
      let sock: WebSocket;
      try {
        // a fresh session token for every start (valid 10 minutes; server/access.py)
        token = (await fetch("/api/session-token").then((r) => r.json())).token;
        sock = await connect();
      } catch {
        lost();
        return;
      }
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
          bench: opts.bench === "ats" ? "ats" : undefined,
          fault,
          token,
        }),
      );
    },
    [connect, lost],
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
  const suggest = useCallback(() => ws.current?.send(JSON.stringify({ action: "suggest" })), []);

  return { state, start, answer, stop, tool, compare, confirmFlags, chooseWiring, suggest };
}

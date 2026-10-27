import { useState } from "react";
import type { Meta } from "../types";
import type { State } from "../useSession";

interface Props {
  meta: Meta | null;
  state: State;
  onStart: (opts: { source: "scenario" | "random"; scenario?: string; effort: string; includeLatent: boolean }) => void;
  onStop: () => void;
}

const STATUS_TEXT: Record<string, string> = {
  idle: "Ready",
  running: "Agent working",
  approval: "Waiting for your approval",
  done: "Finished",
  error: "Error",
};

export function TopBar({ meta, state, onStart, onStop }: Props) {
  const [choice, setChoice] = useState("random");
  const [effort, setEffort] = useState("low");
  const [includeLatent, setIncludeLatent] = useState(false);
  const busy = state.status === "running" || state.status === "approval";

  const start = () =>
    onStart(
      choice === "random"
        ? { source: "random", effort, includeLatent }
        : { source: "scenario", scenario: choice, effort, includeLatent },
    );

  return (
    <header className="topbar">
      <div className="brand">
        <span className="logo">ProbeForge</span>
        <span className="subtitle">AI field electrician, shadow mode</span>
      </div>
      <div className="controls">
        <select value={choice} onChange={(e) => setChoice(e.target.value)} disabled={busy} aria-label="Fault">
          <option value="random">Inject random fault (hidden until the end)</option>
          {meta?.scenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {s.id}: {s.symptom}
            </option>
          ))}
        </select>
        {choice === "random" && (
          <label className="check">
            <input type="checkbox" checked={includeLatent} onChange={(e) => setIncludeLatent(e.target.checked)} disabled={busy} />
            include latent
          </label>
        )}
        <select value={effort} onChange={(e) => setEffort(e.target.value)} disabled={busy} aria-label="Reasoning effort">
          <option value="low">effort low</option>
          <option value="medium">effort medium</option>
        </select>
        {busy ? (
          <button className="btn stop" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button className="btn start" onClick={start} disabled={!meta}>
            Start
          </button>
        )}
      </div>
      <div className="stats">
        <span className={`status status-${state.status}`}>{STATUS_TEXT[state.status]}</span>
        {state.source && <span className="source">{state.source}</span>}
        <span>turn {state.turns}</span>
        <span>{state.measurements} measurements</span>
        <span>{(state.tokens / 1000).toFixed(1)}k tokens</span>
        {state.blocked > 0 && <span className="blocked-count">{state.blocked} blocked</span>}
        <span className="model">{meta?.model}</span>
      </div>
    </header>
  );
}

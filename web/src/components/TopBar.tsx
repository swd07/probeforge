import { useState } from "react";
import type { Meta, Mode } from "../types";
import type { StartOptions, State } from "../useSession";

interface Props {
  meta: Meta | null;
  state: State;
  onStart: (opts: StartOptions) => void;
  onStop: () => void;
}

const STATUS_TEXT: Record<string, string> = {
  idle: "Ready",
  running: "Agent working",
  approval: "Waiting for approval",
  done: "Finished",
  error: "Error",
};

export function TopBar({ meta, state, onStart, onStop }: Props) {
  const [mode, setMode] = useState<Mode>("agent");
  const [choice, setChoice] = useState("random");
  const [effort, setEffort] = useState("low");
  const [includeLatent, setIncludeLatent] = useState(false);
  const [engineer, setEngineer] = useState("");
  const busy = state.status === "running" || state.status === "approval";

  const start = () =>
    onStart({
      mode,
      source: choice === "random" ? "random" : "scenario",
      scenario: choice === "random" ? undefined : choice,
      effort,
      includeLatent,
      engineer,
    });

  const statusText = state.status === "running" && state.mode === "manual" ? "Your turn" : STATUS_TEXT[state.status];

  return (
    <header className="topbar">
      <div className="brand">
        <span className="logo">ProbeForge</span>
        <span className="subtitle">AI field electrician, shadow mode</span>
      </div>
      <div className="controls">
        <div className="segmented" role="tablist" aria-label="Who diagnoses">
          <button className={mode === "agent" ? "on" : ""} onClick={() => setMode("agent")} disabled={busy}>
            Agent
          </button>
          <button className={mode === "manual" ? "on" : ""} onClick={() => setMode("manual")} disabled={busy}>
            Engineer
          </button>
        </div>
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
            latent
          </label>
        )}
        {mode === "agent" ? (
          <select value={effort} onChange={(e) => setEffort(e.target.value)} disabled={busy} aria-label="Reasoning effort">
            <option value="low">effort low</option>
            <option value="medium">effort medium</option>
          </select>
        ) : (
          <input
            className="engineer"
            placeholder="engineer name"
            value={engineer}
            onChange={(e) => setEngineer(e.target.value)}
            disabled={busy}
            aria-label="Engineer name"
          />
        )}
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
        <span className={`status status-${state.status}`}>{statusText}</span>
        {state.source && <span className="source">{state.source}</span>}
        {state.mode === "agent" && <span>turn {state.turns}</span>}
        <span>{state.measurements} measurements</span>
        {state.mode === "agent" && <span>{(state.tokens / 1000).toFixed(1)}k tokens</span>}
        {state.blocked > 0 && <span className="blocked-count">{state.blocked} blocked</span>}
        {state.mode === "agent" && <span className="model">{meta?.model}</span>}
      </div>
    </header>
  );
}

import { useEffect, useState } from "react";
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
  const [engineer, setEngineer] = useState("");
  const [schematic, setSchematic] = useState("saved");
  const busy = state.status === "running" || state.status === "approval";

  // after a run the dropdown is cleared, so it cannot look like the result belongs to whatever it shows;
  // the result card names the fault and the pool that were actually run
  useEffect(() => {
    if (state.status === "done" || state.status === "error") setChoice("");
  }, [state.status]);

  const start = () =>
    onStart({
      mode,
      source: choice === "random" || choice === "clean" ? choice : "scenario",
      scenario: choice === "random" || choice === "clean" ? undefined : choice,
      effort,
      includeLatent: false,
      engineer,
      schematic,
    });

  const statusText =
    state.status === "running" && state.mode === "manual"
      ? "Your turn"
      : state.status === "running" && state.mode === "hybrid"
        ? state.stage ? "Muse Spark working" : "Planner measuring"
        : state.status === "approval" && state.flags
          ? "Confirm the schematic read"
          : STATUS_TEXT[state.status];

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
          <button
            className={mode === "hybrid" ? "on" : ""}
            onClick={() => setMode("hybrid")}
            disabled={busy}
            title="Muse Spark reads the schematic, a planner measures, Muse Spark repairs the netlist and explains"
          >
            Hybrid
          </button>
          <button className={mode === "manual" ? "on" : ""} onClick={() => setMode("manual")} disabled={busy}>
            Engineer
          </button>
        </div>
        <span className="next-run">{busy ? "Running" : "Next run"}</span>
        <select value={choice} onChange={(e) => setChoice(e.target.value)} disabled={busy} aria-label="Fault">
          <option value="" disabled>
            Choose a fault...
          </option>
          <option value="random">Random fault (any of 91)</option>
          <option value="clean">Clean test fault (from holdout_clean.yaml)</option>
          <optgroup label="Scenarios (by symptom)">
            {meta?.scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id}: {s.symptom}
              </option>
            ))}
          </optgroup>
        </select>
        {mode === "hybrid" ? (
          <select value={schematic} onChange={(e) => setSchematic(e.target.value)} disabled={busy} aria-label="Schematic read">
            <option value="saved">saved read (run 2, has errors)</option>
            <option value="photo">saved read of a phone photo (has errors)</option>
            <option value="live">live read by Muse Spark</option>
          </select>
        ) : mode === "agent" ? (
          <select value={effort} onChange={(e) => setEffort(e.target.value)} disabled={busy} aria-label="Reasoning effort">
            <option value="low">effort low</option>
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
          <button className="btn start" onClick={start} disabled={!meta || !choice}>
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

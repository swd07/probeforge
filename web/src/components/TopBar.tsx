import { useEffect, useState } from "react";
import { repairUnderWay } from "../intervention";
import type { AtsMeta, Bench, Meta, Mode } from "../types";
import type { StartOptions, State } from "../useSession";

interface Props {
  meta: Meta | null;
  state: State;
  mode: Mode; // the mode chosen for the next run (App shows its panels before Start)
  setMode: (m: Mode) => void;
  bench: Bench;
  setBench: (b: Bench) => void;
  onStart: (opts: StartOptions) => void;
  onStop: () => void;
  onCompare?: () => void; // after a diagnosis: the other diagnosticians on the same fault
  onSheet?: () => void; // ATS: the troubleshooting sheet
  publicDemo?: boolean; // the public demo: no motor starter bench
}

const STATUS_TEXT: Record<string, string> = {
  idle: "Ready",
  running: "Agent working",
  approval: "Waiting for approval",
  done: "Finished",
  stopped: "Session ended",
  error: "Error",
};

/** ATS: a short label for a scenario's symptom, so the fault list stays readable at 1440 px (the full symptom is the
 * option's tooltip and shows on the panel after Start). Generator stopped (the panel's word) first, then a missing
 * transfer command, then the controller event. */
export function shortSymptom(symptom: string): string {
  if (/generator not started/.test(symptom)) return "generator stopped";
  if (/no transfer command/.test(symptom)) return "no transfer command";
  return /event ([^,]+)/.exec(symptom)?.[1] ?? symptom;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** ATS hybrid: a short label for a saved drawing read, "Saved read, 2 repairs (Oct 31)" (the full description is the
 * option's tooltip and is on the drawing-read card). */
export function shortRead(t: { label: string; recorded: string; repairs: number }): string {
  const kind = t.label.split(/[ ,]/)[0] || "Saved";
  const repairs = t.repairs ? `${t.repairs} repair${t.repairs === 1 ? "" : "s"}` : "no repair";
  const [, m, d] = /^\d{4}-(\d{2})-(\d{2})/.exec(t.recorded) ?? [];
  return `${kind} read, ${repairs}${m ? ` (${MONTHS[Number(m) - 1]} ${Number(d)})` : ""}`;
}

export function TopBar({ meta, state, mode, setMode, bench, setBench, onStart, onStop, onCompare, onSheet, publicDemo = false }: Props) {
  const ats = bench === "ats";
  const [choice, setChoice] = useState("random");
  const [effort, setEffort] = useState("low");
  const [engineer, setEngineer] = useState("");
  const [schematic, setSchematic] = useState("saved");
  const atsMeta = ats ? (meta as AtsMeta | null) : null;
  const [atsRead, setAtsRead] = useState("");
  const atsReadChoice = atsRead || atsMeta?.default_transcription || "";
  const busy = state.status === "running" || state.status === "approval";
  // a repair under way (ATS, after the diagnosis): the first click on Start only asks, for 5 s
  const underway = ats && repairUnderWay({ status: state.status, done: state.done, panel: state.panel as { isolated?: boolean; flow?: number } | null });
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 5000);
    return () => clearTimeout(t);
  }, [armed]);
  useEffect(() => setArmed(false), [underway, state.status]);
  const shown = busy || state.status === "done" ? state.mode : mode; // run statistics belong to the run's mode

  // after a run the dropdown is cleared, so it cannot look like the result belongs to whatever it shows;
  // the result card names the fault and the pool that were actually run
  useEffect(() => {
    if (state.status === "done" || state.status === "error") setChoice("");
  }, [state.status]);

  const start = () => {
    if (ats && mode === "hybrid" && atsReadChoice === "live" &&
        !window.confirm(`Re-read the drawing live with Muse Spark?\n\nCost and time: ${atsMeta?.live_read.estimate}. The read is reused for later runs in this server.`))
      return;
    onStart({
      mode,
      source: choice === "random" || choice === "clean" ? choice : "scenario",
      scenario: choice === "random" || choice === "clean" ? undefined : choice,
      effort,
      includeLatent: false,
      engineer,
      schematic: ats ? atsReadChoice : schematic,
      bench,
    });
  };

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
      <div className="brand" title="AI field electrician, shadow mode">
        <span className="logo">ProbeForge</span>
      </div>
      <div className="controls">
        <div className="segmented bench" role="tablist" aria-label="Bench">
          {!publicDemo && (
            <button className={!ats ? "on" : ""} onClick={() => { setBench("star_delta"); setChoice("random"); }} disabled={busy}
                    title="Level 1: star-delta reversing motor starter">
              Motor starter
            </button>
          )}
          <button className={ats ? "on" : ""} onClick={() => { setBench("ats"); setChoice("random"); }}
                  disabled={busy} title="Level 2: ASCO Series 300 Group G automatic transfer switch (our redrawing of 978741)">
            ATS
          </button>
        </div>
        <div className="segmented" role="tablist" aria-label="Who diagnoses">
          <button className={mode === "agent" ? "on" : ""} onClick={() => setMode("agent")} disabled={busy}>
            Agent
          </button>
          <button
            className={mode === "hybrid" ? "on" : ""}
            onClick={() => setMode("hybrid")}
            disabled={busy}
            title={ats ? "Hybrid v2: Muse Spark's transcription of the drawing sheets, an information-gain planner measures, Muse Spark explains"
                       : "Muse Spark reads the schematic, a planner measures, Muse Spark repairs the netlist and explains"}
          >
            Hybrid
          </button>
          <button className={mode === "manual" ? "on" : ""} onClick={() => setMode("manual")} disabled={busy}>
            Engineer
          </button>
        </div>
        <span className="next-run">{busy ? "Running" : "Next run"}</span>
        <select className="fault" value={choice} onChange={(e) => setChoice(e.target.value)} disabled={busy} aria-label="Fault"
                title={meta?.scenarios.find((s) => s.id === choice)?.symptom}>
          <option value="" disabled>
            Choose a fault...
          </option>
          {ats ? (
            <option value="random" title="Any catalog fault visible on the controller panel">Random fault</option>
          ) : (
            <>
              <option value="random">Random fault (any of 91)</option>
              <option value="clean">Clean test fault (from holdout_clean.yaml)</option>
            </>
          )}
          <optgroup label={ats ? "ATS dev scenarios (by symptom)" : "Scenarios (by symptom)"}>
            {meta?.scenarios.map((s) => (
              <option key={s.id} value={s.id} title={s.symptom}>
                {s.id}: {ats ? shortSymptom(s.symptom) : s.symptom}
              </option>
            ))}
          </optgroup>
        </select>
        {mode === "hybrid" && ats ? (
          <select className="read" value={atsReadChoice} onChange={(e) => setAtsRead(e.target.value)} disabled={busy} aria-label="Drawing read"
                  title={atsMeta?.transcriptions.find((t) => t.id === atsReadChoice)?.label}>
            {atsMeta?.transcriptions.map((t) => (
              <option key={t.id} value={t.id} title={`${t.label} (recorded ${t.recorded})`}>
                {shortRead(t)}
              </option>
            ))}
            <option value="live" disabled={!atsMeta?.live_read.available}
                    title={atsMeta?.live_read.available ? atsMeta.live_read.estimate : atsMeta?.live_read.reason}>
              Live re-read{atsMeta?.live_read.available ? "" : ` (${atsMeta?.live_read.short ?? "unavailable"})`}
            </option>
          </select>
        ) : mode === "hybrid" ? (
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
          <button
            className="btn stop"
            title="End this session (this is not the Stop push button on the panel)"
            onClick={() => {
              if (
                state.mode === "manual" &&
                !window.confirm(
                  ats
                    ? "End this engineer session? Your steps so far are not saved as a diagnosis."
                    : "End this engineer session? Your steps so far are not saved as a diagnosis.\n\n(To stop the motor, use the red Stop button on the front panel instead.)",
                )
              )
                return;
              onStop();
            }}
          >
            End session
          </button>
        ) : (
          <button className={`btn start ${armed ? "armed" : ""}`} disabled={!meta || !choice}
                  onClick={underway && !armed ? () => setArmed(true) : start}
                  title={underway ? "A repair is under way: the first click asks, a second click within 5 s ends it and starts a new run" : undefined}>
            {armed ? "End the repair and start new?" : "Start"}
          </button>
        )}
        <button className="btn ghost" onClick={onCompare} disabled={!onCompare}
                title="After a diagnosis: the other diagnosticians on the same fault, side by side">
          Compare
        </button>
        {onSheet && (
          <button className="btn ghost sheet" onClick={onSheet} title="Generated from the simulator, not reviewed by an engineer">
            Troubleshooting sheet
          </button>
        )}
      </div>
      {/* two fixed rows that never wrap, so the top bar keeps its height whatever the status says */}
      <div className="stats">
        <div className="stats-row" title={state.source || undefined}>
          <span className={`status status-${state.status}`}>{statusText}</span>
          {state.source && <span className="source">{state.source}</span>}
        </div>
        <div className="stats-row">
          {shown === "agent" && <span>turn {state.turns}</span>}
          <span>{state.measurements} measurements</span>
          {shown === "agent" && <span>{(state.tokens / 1000).toFixed(1)}k tokens</span>}
          {state.blocked > 0 && <span className="blocked-count">{state.blocked} blocked</span>}
          {shown !== "manual" && <span className="model">{meta?.model}</span>}
        </div>
      </div>
    </header>
  );
}

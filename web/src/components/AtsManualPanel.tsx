import { useMemo, useState } from "react";
import type { AtsMeta, AtsPanel, FeedItem, Probe } from "../types";
import { describeTool } from "./Feed";
import type { MeterState } from "./ManualPanel";

interface Props {
  meta: AtsMeta | null;
  panel: AtsPanel | null;
  meter: MeterState;
  setMeter: (m: MeterState) => void;
  lastProbe: Probe | null;
  feed: FeedItem[];
  diagnosing: boolean; // engineer session before the diagnosis
  intervention: boolean; // after the diagnosis: the authorized person isolates, repairs, restores
  started: boolean;
  stopped: boolean;
  onTool: (name: string, args: Record<string, unknown>) => void;
  onDiagnose: () => void;
}

function hint(p: AtsPanel | null, started: boolean, stopped: boolean, diagnosing: boolean, intervention: boolean): string {
  if (stopped) return "Session ended. Pick a fault and press Start to begin a new one.";
  if (!started || !p) return "Pick a fault and press Start. The Normal source has failed 60 s before you arrive.";
  if (intervention) {
    if (p.flow >= 5) return "Transfer verified by the simulator: the load is on Emergency with the position confirmed. The UPS countdown has stopped.";
    if (p.flow >= 4) return "Sources restored: the controller repeats its sequence. Wait and watch the panel until the transfer is verified.";
    return p.isolated
      ? "Sources isolated. Request the repair that removes the root cause, then Restore sources (strong approval: cite a reading)."
      : "Authorized intervention: isolate the sources (lockout / tagout), request the repair, then restore and verify the transfer.";
  }
  if (diagnosing && p.isolated)
    return "Both sources are isolated: the ohmmeter works now. The manual operation check moves the switch to the other position and back, with readings there.";
  return "Measure volts between two points: click them on the drawing, then Measure. Resistance and the manual operation check need both sources isolated. A repeat transfer takes a reading during the command (strong approval).";
}

/** The engineer's instruments on the ATS bench (same tools and policy as the agent), and the authorized intervention
 * after any diagnosis. Strong-approval requests must cite at least one executed reading; the policy refuses them
 * otherwise before they reach the approver. */
export function AtsManualPanel({ meta, panel, meter, setMeter, lastProbe, feed, diagnosing, intervention, started, stopped, onTool, onDiagnose }: Props) {
  const [cited, setCited] = useState<Set<number>>(new Set());
  const [repair, setRepair] = useState("replace_coil");
  const [target, setTarget] = useState("");
  const [waitS, setWaitS] = useState(30);
  const active = diagnosing || intervention;
  const readings = useMemo(
    () =>
      feed.flatMap((f) => {
        if (f.kind !== "tool" || !f.ev.executed || f.ev.probes.length === 0) return [];
        const { title, detail } = describeTool(f.ev);
        return [{ step: f.ev.step, text: `${title}${detail ? ": " + detail : ""}` }];
      }),
    [feed],
  );
  const targets = meta?.repairs[repair] ?? [];
  const send = (name: string, extra: Record<string, unknown> = {}) =>
    onTool(name, { reason: meter.reason, evidence_steps: [...cited], ...extra });
  const pair = meter.a && meter.b ? [{ point_a: meter.a, point_b: meter.b }] : [];
  const measure = () => {
    if (!meter.a || !meter.b) return;
    onTool(meter.kind === "V" ? "measure_voltage" : "measure_resistance", { point_a: meter.a, point_b: meter.b });
    setMeter({ ...meter, a: null, b: null });
  };
  const reading = lastProbe
    ? lastProbe.kind === "R"
      ? lastProbe.value === "open"
        ? "OPEN"
        : `${lastProbe.value} Ω`
      : `${lastProbe.value} V`
    : "---";

  return (
    <section className="hyp-card manual-card">
      <div className="card-title">
        <span>{intervention ? "Authorized intervention" : "Your instruments"}</span>
        <span className="muted">same tools and policy as the agent</span>
      </div>
      <div className="next-step">
        <b>Next:</b> {hint(panel, started, stopped, diagnosing, intervention)}
      </div>
      <div className="meter">
        <div className="meter-display">
          <span className="meter-value">{reading}</span>
          <span className="meter-sub">{lastProbe ? `${lastProbe.a} → ${lastProbe.b}` : "click two points on the drawing"}</span>
        </div>
        <div className="meter-controls">
          <div className="segmented small">
            <button className={meter.kind === "V" ? "on" : ""} onClick={() => setMeter({ ...meter, kind: "V" })}>V</button>
            <button className={meter.kind === "R" ? "on" : ""} onClick={() => setMeter({ ...meter, kind: "R" })}>{"Ω"}</button>
          </div>
          <span className={`probe-slot ${meter.a ? "set" : ""}`}>A: {meter.a ?? "-"}</span>
          <span className={`probe-slot ${meter.b ? "set" : ""}`}>B: {meter.b ?? "-"}</span>
          <button className="btn small primary" disabled={!active || !meter.a || !meter.b} onClick={measure}>Measure</button>
          <button className="btn small ghost" onClick={() => setMeter({ ...meter, a: null, b: null })}>Clear</button>
        </div>
      </div>
      <div className="manual-row">
        <button className="btn small ghost" disabled={!active} onClick={() => onTool("read_panel", {})}>Read panel</button>
        <button className="btn small ghost" disabled={!active} onClick={() => onTool("read_event_log", {})}>Event log</button>
        <button className="btn small ghost" disabled={!active} onClick={() => onTool("read_metering", {})}>Metering</button>
        <button className="btn small ghost" disabled={!active} onClick={() => onTool("read_position_indicator", {})}
                title="Look at the position flag on the mechanism (a reading: 30 s, the same tool as the agent's)">
          Position indicator
        </button>
        <select value={waitS} onChange={(e) => setWaitS(Number(e.target.value))} aria-label="Wait seconds">
          {[10, 30, 60, 120].map((s) => <option key={s} value={s}>{s} s</option>)}
        </select>
        <button className="btn small ghost" disabled={!active} onClick={() => onTool("wait", { seconds: waitS })}>Wait</button>
      </div>
      <label className="reason-row">
        Reason (sent with requests that need approval)
        <input className="reason" value={meter.reason} onChange={(e) => setMeter({ ...meter, reason: e.target.value })} placeholder="why you need it" />
      </label>
      <div className="cite">
        <span className="muted">Cite readings (required for strong approval):</span>
        {readings.length === 0 && <span className="muted"> none yet: measure first</span>}
        {readings.map((r) => (
          <button
            key={r.step}
            className={`chip ${cited.has(r.step) ? "on" : ""}`}
            onClick={() => setCited((s) => { const n = new Set(s); n.has(r.step) ? n.delete(r.step) : n.add(r.step); return n; })}
            title={r.text}
          >
            #{r.step}
          </button>
        ))}
      </div>
      <div className="manual-row">
        <button className="btn small ghost" disabled={!active || !!panel?.isolated} onClick={() => send("isolate_sources")}>Isolate sources</button>
        <button className="btn small ghost" disabled={!active || !panel?.isolated} onClick={() => send("restore_sources")}>Restore sources</button>
        {diagnosing && (
          <>
            <button className="btn small ghost" disabled={!panel?.isolated} onClick={() => send("manual_operation_check", { readings: meter.kind === "R" ? pair : [] })}
                    title="Both sources isolated: operate the switch to the other position, read the meter pair (Ω) there, operate it back">
              Manual operation check{meter.kind === "R" && pair.length ? " + Ω A-B" : ""}
            </button>
            <button className="btn small ghost" disabled={!!panel?.isolated} onClick={() => send("repeat_transfer_attempt", { measure_during: meter.kind === "V" ? pair : [] })}
                    title="After a Transfer Failure: repeat the transfer command and read the meter pair (V) while it is active. Strong approval.">
              Repeat transfer{meter.kind === "V" && pair.length ? " + V A-B during command" : ""}
            </button>
          </>
        )}
      </div>
      {intervention && (
        <div className="manual-row">
          <select value={repair} onChange={(e) => { setRepair(e.target.value); setTarget(""); }} aria-label="Repair">
            {Object.keys(meta?.repairs ?? {}).map((a) => <option key={a} value={a}>{a.replace(/_/g, " ")}</option>)}
          </select>
          <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Part">
            <option value="" disabled>part...</option>
            {targets.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <button className="btn small primary" disabled={!panel?.isolated || !target} onClick={() => send("perform_action", { action: repair, target })}>
            Request repair
          </button>
        </div>
      )}
      {diagnosing && (
        <div className="manual-row">
          <button className="btn small primary diagnose" onClick={onDiagnose}>Diagnose...</button>
        </div>
      )}
      <p className="muted hint">
        A = B is refused. Points inside the controller (between its relay contacts) cannot be probed. Every reading or
        action takes 30 s of virtual time and the UPS keeps draining.
      </p>
    </section>
  );
}

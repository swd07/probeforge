import type { Meta, Panel, Probe } from "../types";

export interface MeterState {
  kind: "V" | "R";
  a: string | null;
  b: string | null;
  hold: number;
  wait: number;
  reason: string;
}

interface Props {
  meta: Meta | null;
  panel: Panel | null;
  meter: MeterState;
  setMeter: (m: MeterState) => void;
  lastProbe: Probe | null;
  active: boolean;
  started: boolean;
  done: boolean;
  steps: number;
  onTool: (name: string, args: Record<string, unknown>) => void;
  onDiagnose: () => void;
}

/** One short hint about the next sensible step, from what the engineer can see on the panel. */
function nextStep(panel: Panel | null, started: boolean, done: boolean, steps: number): string {
  if (done) return "Diagnosis submitted. Compare runs the baseline and the agent on the same fault (the agent costs about $0.07).";
  if (!started || !panel)
    return "Pick a fault and press Start. Until then no panel is loaded, so the front panel shows QF1 OFF and every lamp dark.";
  if (panel.lamps?.Fault)
    return "The Fault lamp is on: the motor overload KK1 has tripped. Find out why, or press Reset KK1 (it needs approval), then try the start buttons again.";
  if (!panel.power)
    return steps === 0
      ? "QF1 (main breaker) is OFF: the panel is dead. Click QF1 on the front panel to switch it on and see the symptoms."
      : "QF1 is OFF: the panel is dead, so use the ohmmeter (Ω) now. Voltage needs QF1 ON. Switching on again after a fuse or breaker trip needs approval.";
  if (steps === 0)
    return "The fault is already in the panel and QF1 is ON, as on a panel reported faulty. Look at the lamps and the motor, then press Start Fwd or Start Rev on the front panel and watch what happens.";
  return "Measure volts between two points: click them on the schematic, then Measure. In a live circuit an open contact shows about 230 V across it, a closed one 0 V. For ohms switch QF1 off. When you know the fault, press Diagnose.";
}

/** The engineer's instruments: a meter (click two points on the schematic), hold time for the panel
 * buttons, wait, a reason for requests that need approval, and the diagnosis form. */
export function ManualPanel({ meta, panel, meter, setMeter, lastProbe, active, started, done, steps, onTool, onDiagnose }: Props) {
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
        <span>Your instruments</span>
        <span className="muted">same tools and policy as the agent</span>
      </div>
      <div className="next-step">
        <b>Next:</b> {nextStep(panel, started, done, steps)}
      </div>
      <div className="meter">
        <div className="meter-display">
          <span className="meter-value">{reading}</span>
          <span className="meter-sub">{lastProbe ? `${lastProbe.a} → ${lastProbe.b}` : "click two points on the schematic"}</span>
        </div>
        <div className="meter-controls">
          <div className="segmented small">
            <button className={meter.kind === "V" ? "on" : ""} onClick={() => setMeter({ ...meter, kind: "V" })}>
              V
            </button>
            <button className={meter.kind === "R" ? "on" : ""} onClick={() => setMeter({ ...meter, kind: "R" })}>
              {"Ω"}
            </button>
          </div>
          <span className={`probe-slot ${meter.a ? "set" : ""}`}>A: {meter.a ?? "-"}</span>
          <span className={`probe-slot ${meter.b ? "set" : ""}`}>B: {meter.b ?? "-"}</span>
          <button className="btn small primary" disabled={!active || !meter.a || !meter.b} onClick={measure}>
            Measure
          </button>
          <button className="btn small ghost" onClick={() => setMeter({ ...meter, a: null, b: null })}>
            Clear
          </button>
        </div>
      </div>
      <div className="manual-row">
        <label>
          Button hold
          <select value={meter.hold} onChange={(e) => setMeter({ ...meter, hold: Number(e.target.value) })}>
            {[0.2, 1, 3, 7].map((s) => (
              <option key={s} value={s}>
                {s} s
              </option>
            ))}
          </select>
        </label>
        <label>
          Wait
          <select value={meter.wait} onChange={(e) => setMeter({ ...meter, wait: Number(e.target.value) })}>
            {[1, 3, 6, 10].map((s) => (
              <option key={s} value={s}>
                {s} s
              </option>
            ))}
          </select>
        </label>
        <button className="btn small ghost" disabled={!active} onClick={() => onTool("wait", { seconds: meter.wait })}>
          Wait
        </button>
        <button className="btn small ghost" disabled={!active} onClick={() => onTool("read_indicators", {})}>
          Read panel
        </button>
      </div>
      <label className="reason-row">
        Reason (sent with requests that need approval)
        <input
          className="reason"
          value={meter.reason}
          onChange={(e) => setMeter({ ...meter, reason: e.target.value })}
          placeholder="why you need it"
        />
      </label>
      <div className="manual-row">
        <button
          className="btn small ghost"
          disabled={!active}
          onClick={() => onTool("set_power", { on: !panel?.power, reason: meter.reason })}
        >
          Power {panel?.power ? "off" : "on"}
        </button>
        {meta?.thermal_relays.map((kk) => (
          <button
            key={kk}
            className="btn small ghost"
            disabled={!active}
            onClick={() => onTool("perform_action", { action: "reset_protection", target: kk, reason: meter.reason })}
          >
            Reset {kk}
          </button>
        ))}
        <button className="btn small primary diagnose" disabled={!active} onClick={onDiagnose}>
          Diagnose...
        </button>
      </div>
      <p className="muted hint">
        The Start, Stop and QF1 controls on the front panel are clickable. Voltage needs QF1 ON, resistance QF1 OFF;
        the safety policy blocks the other way round, as on a real panel.
      </p>
    </section>
  );
}

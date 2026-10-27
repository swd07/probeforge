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
  onTool: (name: string, args: Record<string, unknown>) => void;
  onDiagnose: () => void;
}

/** The engineer's instruments: a meter (click two points on the schematic), hold time for the panel
 * buttons, wait, a reason for requests that need approval, and the diagnosis form. */
export function ManualPanel({ meta, panel, meter, setMeter, lastProbe, active, onTool, onDiagnose }: Props) {
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
      <div className="manual-row">
        <input
          className="reason"
          value={meter.reason}
          onChange={(e) => setMeter({ ...meter, reason: e.target.value })}
          placeholder="reason for requests that need approval"
        />
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
      <p className="muted hint">Panel buttons and the breaker on the front panel are clickable. Resistance needs the power off.</p>
    </section>
  );
}

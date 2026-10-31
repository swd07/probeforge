import type { AtsMeta, AtsPanel as Panel } from "../types";

const LIGHTS: [string, string][] = [
  ["Normal accepted", "green"],
  ["Emergency accepted", "red"],
  ["Load on Normal", "green"],
  ["Load on Emergency", "red"],
  ["Alert", "amber"],
  ["Not in automatic", "amber"],
];

const mmss = (s: number) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.floor(Math.max(0, s) % 60)).padStart(2, "0")}`;

interface Props {
  meta: AtsMeta | null;
  panel: Panel | null;
  /** Engineer mode: the position only as last checked with the position indicator tool (undefined: always shown). */
  checkedPosition?: string | null;
}

function UpsClock({ meta, panel: p }: Props) {
  const autonomy = p?.ups.autonomy_s ?? meta?.ups_autonomy_s ?? 600;
  const left = p?.ups.left_s ?? autonomy;
  const verified = (p?.flow ?? 0) >= 5;
  const state = verified ? "countdown stopped: transfer verified" : p?.ups.depleted ? "UPS depleted" : p?.ups.draining ? "draining" : "not draining";
  return (
    <div className={`st-ups ${p?.ups.draining && !verified ? "draining" : ""} ${p?.ups.depleted ? "depleted" : ""}`}
         title={`Simulation parameter: ${autonomy / 60} min autonomy (within the 1 to 15 min data center range, Schneider Electric, source S7 in ATS_MODEL.md), ${meta?.action_s ?? 30} s per reading or action.`}>
      <div className="st-label">UPS time left</div>
      <div className="st-clock">{mmss(left)}</div>
      <div className="ups-track"><div className="ups-bar" style={{ width: `${(100 * left) / autonomy}%` }} /></div>
      <div className="muted">{state}</div>
    </div>
  );
}

function Sources({ panel: p }: Props) {
  return (
    <div className="st-block">
      <div className="st-label">Sources</div>
      <div className={`src ${p?.normal_source === "available" ? "ok" : "bad"}`}>
        Normal: {p ? p.normal_source : "-"}{p?.isolated && <em> 52U open</em>}
      </div>
      <div className={`src ${p?.generator === "running" ? "ok" : p?.generator === "stopped" ? "off" : "warn"}`}>
        Generator: {p ? p.generator : "-"}{p?.isolated && <em> locked out</em>}
      </div>
    </div>
  );
}

function SwitchLoad({ panel: p, checkedPosition }: Props) {
  return (
    <div className="st-block">
      <div className="st-label">Transfer switch</div>
      <div className="src">
        Position:{" "}
        {checkedPosition === undefined ? <b>{p ? p.position : "-"}</b>
          : checkedPosition ? <b title="as last checked on the indicator">{checkedPosition}</b>
          : <span className="muted">not checked (Position indicator)</span>}
      </div>
      <div className={`src ${p?.load_powered && !p?.load_lost ? "ok" : "bad"} ${p?.load_lost ? "lost" : ""}`}>
        Critical load:{" "}
        {!p ? "-" : p.load_lost && !p.load_powered ? <b>LOST (UPS depleted at {mmss(p.ups.depleted_after_outage_s ?? 0)})</b>
          : p.load_lost ? `powered again (lost at ${mmss(p.ups.depleted_after_outage_s ?? 0)})`
          : p.load_powered ? "powered" : "on UPS"}
      </div>
    </div>
  );
}

function Display({ panel: p }: Props) {
  return (
    <div className="st-block">
      <div className="st-label">Controller display</div>
      <div className="ats-display">{p ? p.display : "----"}</div>
      {p && p.alarms.length > 0 && <div className="ats-alarms">Alarm: {p.alarms.join(", ")}</div>}
    </div>
  );
}

function Stages({ meta, panel: p, vertical = false }: Props & { vertical?: boolean }) {
  return (
    <div className={`ats-flow ${vertical ? "vertical" : ""}`} aria-label="UPS status">
      {(meta?.flow ?? []).map((f, i) => (
        <span key={f} className={`flow-step ${p && i < p.flow ? "past" : ""} ${p && i === p.flow ? "now" : ""}`}>{f}</span>
      ))}
    </div>
  );
}

function Lights({ panel: p }: Props) {
  return (
    <div className="ats-lights">
      {LIGHTS.map(([name, color]) => (
        <span key={name} className="ats-light"><i className={`lamp small ${color} ${p?.lights[name] ? "on" : ""}`} />{name}</span>
      ))}
    </div>
  );
}

function Metering({ panel: p }: Props) {
  return (
    <table className="metering">
      <thead><tr><th /><th>A-B</th><th>B-C</th><th>C-A</th></tr></thead>
      <tbody>
        {(["Normal", "Emergency"] as const).map((s) => (
          <tr key={s}><td>{s}</td>{(p?.metering[s] ?? [0, 0, 0]).map((v, i) => <td key={i}>{p ? v : "-"}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

function Events({ panel: p }: Props) {
  return (
    <ol className="event-log">
      {(p?.events ?? []).slice(-8).map((e, i) => (
        <li key={i}><span className="t">{e.t.toFixed(1)} s</span> {e.event}{e.cause && <span className="muted"> ({e.cause})</span>}</li>
      ))}
      {!p && <li className="muted">Pick a fault and press Start.</li>}
    </ol>
  );
}

/** The status column left of the drawing; the action limits open as a modal (they need the width). */
export function AtsStatusColumn({ onLimits, ...props }: Props & { onLimits: () => void }) {
  return (
    <section className="st-column">
      <UpsClock {...props} />
      <Sources {...props} />
      <SwitchLoad {...props} />
      <div className="st-block">
        <div className="st-label">Group G controller</div>
        <Lights {...props} />
      </div>
      <Display {...props} />
      <Stages {...props} vertical />
      <details className="st-fold"><summary>Metering screen</summary><Metering {...props} /></details>
      <details className="st-fold"><summary>Event log</summary><Events {...props} /></details>
      <button className="btn ghost small limits-open" onClick={onLimits}>Agent action limits (from the policy code)</button>
    </section>
  );
}

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

/** The installation as a technician at the switch sees it: sources, transfer switch, load, UPS, and the Group G
 * controller face (lights, display, metering screen, event log). The UPS status flow ends at "Transfer verified",
 * set only when the simulator confirms the load on Emergency with the position confirmed. */
/** checkedPosition: Engineer mode shows the mechanism position only as last checked with the position indicator tool
 * (the agent has the same tool), so both diagnose with the same information. Undefined: always shown. */
export function AtsPanel({ meta, panel, checkedPosition }: { meta: AtsMeta | null; panel: Panel | null; checkedPosition?: string | null }) {
  const flow = meta?.flow ?? [];
  const p = panel;
  const autonomy = p?.ups.autonomy_s ?? meta?.ups_autonomy_s ?? 600;
  const left = p?.ups.left_s ?? autonomy;
  const verified = (p?.flow ?? 0) >= 5;
  return (
    <section className="ats-panel">
      <div className="ats-flow" aria-label="UPS status">
        {flow.map((f, i) => (
          <span key={f} className={`flow-step ${p && i < p.flow ? "past" : ""} ${p && i === p.flow ? "now" : ""}`}>
            {f}
          </span>
        ))}
      </div>
      <div className="ats-grid">
        <div className="ats-box">
          <div className="box-title">Sources</div>
          <div className={`src ${p?.normal_source === "available" ? "ok" : "bad"}`}>
            Normal (utility): {p ? p.normal_source : "-"}
            {p?.isolated && <em> 52U open, locked out</em>}
          </div>
          <div className={`src ${p?.generator === "running" ? "ok" : p?.generator === "stopped" ? "off" : "warn"}`}>
            Emergency (generator): {p ? p.generator : "-"}
            {p?.isolated && <em> locked out</em>}
          </div>
        </div>
        <div className="ats-box">
          <div className="box-title">Transfer switch and load</div>
          <div className="src">
            Position:{" "}
            {checkedPosition === undefined ? (
              <>
                <b>{p ? p.position : "-"}</b> <span className="muted">(mechanism flag at the switch)</span>
              </>
            ) : checkedPosition ? (
              <>
                <b>{checkedPosition}</b> <span className="muted">(as last checked on the indicator)</span>
              </>
            ) : (
              <span className="muted">not checked: use Position indicator (a reading, as for the agent)</span>
            )}
          </div>
          <div className={`src ${p?.load_powered ? "ok" : "bad"}`}>Critical load: {p ? (p.load_powered ? "powered" : "on UPS") : "-"}</div>
        </div>
        <div className={`ats-box ups ${p?.ups.draining && !verified ? "draining" : ""} ${p?.ups.depleted ? "depleted" : ""}`}>
          <div className="box-title">UPS time left</div>
          <div className="ups-time">{mmss(left)}</div>
          <div className="ups-track">
            <div className="ups-bar" style={{ width: `${(100 * left) / autonomy}%` }} />
          </div>
          <div className="muted">
            {verified ? "countdown stopped: transfer verified" : p?.ups.depleted ? "UPS depleted" : p?.ups.draining ? "draining" : "not draining"}.
            Simulation parameter: {autonomy / 60} min autonomy, {meta?.action_s ?? 30} s per reading or action.
          </div>
        </div>
      </div>
      <div className="ats-grid controller">
        <div className="ats-box face">
          <div className="box-title">Group G controller</div>
          <div className="ats-lights">
            {LIGHTS.map(([name, color]) => (
              <span key={name} className="ats-light">
                <i className={`lamp small ${color} ${p?.lights[name] ? "on" : ""}`} />
                {name}
              </span>
            ))}
          </div>
          <div className="ats-display">{p ? p.display : "----"}</div>
          {p && p.alarms.length > 0 && <div className="ats-alarms">Alarm: {p.alarms.join(", ")}</div>}
        </div>
        <div className="ats-box">
          <div className="box-title">Metering screen (V, line to line)</div>
          <table className="metering">
            <thead>
              <tr>
                <th />
                <th>A-B</th>
                <th>B-C</th>
                <th>C-A</th>
              </tr>
            </thead>
            <tbody>
              {(["Normal", "Emergency"] as const).map((s) => (
                <tr key={s}>
                  <td>{s}</td>
                  {(p?.metering[s] ?? [0, 0, 0]).map((v, i) => (
                    <td key={i}>{p ? v : "-"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="ats-box events">
          <div className="box-title">Event log</div>
          <ol className="event-log">
            {(p?.events ?? []).slice(-8).map((e, i) => (
              <li key={i}>
                <span className="t">{e.t.toFixed(1)} s</span> {e.event}
                {e.cause && <span className="muted"> ({e.cause})</span>}
              </li>
            ))}
            {!p && <li className="muted">Pick a fault and press Start.</li>}
          </ol>
        </div>
      </div>
    </section>
  );
}

/** The agent action limits, generated from the ATS policy code (the same table as docs/ATS_MODEL.md). */
export function LimitsTable({ meta }: { meta: AtsMeta | null }) {
  if (!meta) return null;
  return (
    <details className="limits">
      <summary>Agent action limits (from the policy code)</summary>
      <table>
        <tbody>
          {meta.limits.map((l, i) => (
            <tr key={i} className={`tier-${l.tier.replace(" ", "-")}`}>
              <td>{l.action}</td>
              <td className="tier">{l.tier}</td>
              <td>{l.condition}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

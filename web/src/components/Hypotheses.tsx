import type { Hypothesis } from "../types";
import { hypKey } from "../useSession";

export function Hypotheses({ hypotheses, previous }: { hypotheses: Hypothesis[]; previous: Record<string, number> }) {
  const top = hypotheses.slice(0, 6);
  return (
    <section className="hyp-card">
      <div className="card-title">
        <span>Hypotheses</span>
        <span className="muted">updated after each measurement</span>
      </div>
      {top.length === 0 && <div className="muted empty">No hypotheses yet.</div>}
      <ul className="hyp-list">
        {top.map((h, i) => {
          const key = hypKey(h);
          const prev = previous[key];
          const delta = prev === undefined ? null : h.probability - prev;
          return (
            <li key={key} className={i === 0 ? "lead" : ""} title={h.reason}>
              <div className="hyp-head">
                <span className="hyp-name">
                  {h.component}
                  {h.part ? ` ${h.part}` : ""} <em>{h.failure_mode.replace("_", " ")}</em>
                </span>
                <span className="hyp-p">
                  {(h.probability * 100).toFixed(0)}%
                  {delta !== null && Math.abs(delta) >= 0.01 && <span className={delta > 0 ? "up" : "down"}>{delta > 0 ? " ▲" : " ▼"}</span>}
                  {prev === undefined && <span className="new"> new</span>}
                </span>
              </div>
              <div className="hyp-track">
                <div className="hyp-bar" style={{ width: `${Math.max(2, h.probability * 100)}%` }} />
              </div>
              {i === 0 && <div className="hyp-reason">{h.reason}</div>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

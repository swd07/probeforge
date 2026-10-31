import { useState } from "react";
import type { AtsTranscription, ModelCheck, NextStep } from "../types";

const pct = (x: number) => `${(x * 100).toFixed(0)}%`;

/** Model text is shown as written, except dashes used as punctuation (project style rule). */
const plain = (text: string) => text.replace(/\s*[—–]\s*/g, ", ");

/** ATS hybrid: which transcription the run uses, the model step (fault-free sequence check and the repair log) and
 * the read quality per version. Read quality is scored against our redrawing, for evaluation only: the pipeline never
 * sees it. */
export function AtsTranscriptionCard({ t, check }: { t: AtsTranscription; check: ModelCheck | null }) {
  const [open, setOpen] = useState(true);
  return (
    <section className="hyp-card ats-hybrid-card">
      <button className="card-title plain-button" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>Drawing read and model</span>
        <span className="muted">
          {t.label} {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="ats-hybrid-body">
          <div className="kv">
            <span>Transcription</span>
            <span>
              {t.run_id}, recorded {t.recorded}: {t.reads} Muse Spark reads of 7 drawing-sheet crops, {t.components} components,{" "}
              {t.nets} nets, {t.flags} flagged regions
              {t.cost_usd !== null && t.cost_usd !== undefined && <> (cost when recorded ${t.cost_usd.toFixed(3)})</>}
            </span>
          </div>
          <div className="kv">
            <span>Model check</span>
            <span className={check ? (check.ok ? "ok-text" : "bad-text") : "muted"}>
              {check
                ? check.ok
                  ? `documented fault-free sequence reproduced (${check.events.length} of ${check.expected.length} events in order)`
                  : `fault-free sequence not reproduced: ${check.events.join(", ")}`
                : "checking..."}
            </span>
          </div>
          <div className="kv">
            <span>Repair log</span>
            <span>
              {t.attempts.length === 0
                ? "no repair needed: the first model passed the sequence check"
                : `${t.repairs} accepted of ${t.attempts.length} proposals (when recorded)`}
              {t.stopped && <em> ({t.stopped})</em>}
            </span>
          </div>
          {t.attempts.length > 0 && (
            <ol className="repair-log">
              {t.attempts.map((a, i) => (
                <li key={i} className={a.rejected ? "rejected" : "accepted"}>
                  <div className="repair-where">
                    <b>Check found:</b> {t.where[i] ?? a.problem.split(". Simulating your transcription, ")[1]?.split(". Check that")[0] ?? a.problem}
                  </div>
                  <div>
                    <b>Muse Spark changed:</b> {plain(a.explanation || "(no explanation)")}
                  </div>
                  {a.diff.length > 0 && (
                    <pre className="diff">
                      {a.diff.map((line, k) => (
                        <span key={k} className={line.startsWith("+") ? "add" : "del"}>
                          {line}
                          {"\n"}
                        </span>
                      ))}
                    </pre>
                  )}
                  <div className={a.rejected ? "bad-text" : "ok-text"}>{a.rejected ? `rejected: ${a.rejected}` : `accepted: ${a.accepted}`}</div>
                </li>
              ))}
            </ol>
          )}
          {t.read_quality.length > 0 && (
            <table className="quality">
              <thead>
                <tr>
                  <th>Read quality (vs our redrawing, evaluation only)</th>
                  <th>connections P / R</th>
                  <th>relay contacts</th>
                  <th>nets exact</th>
                </tr>
              </thead>
              <tbody>
                {t.read_quality.map((q) => (
                  <tr key={q.version} className={q.worse ? "worse" : ""}>
                    <td>
                      {q.version}
                      {q.worse && <em> worse than before</em>}
                    </td>
                    <td>
                      {pct(q.connections_precision)} / {pct(q.connections_recall)}
                    </td>
                    <td title={q.relay_contacts_wrong.length ? `wrong: ${q.relay_contacts_wrong.join(", ")}` : "all right"}>
                      {q.relay_contacts_right} of {q.relay_contacts_true}
                    </td>
                    <td>{q.nets_exact}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted disclosure">{t.disclosure}</p>
        </div>
      )}
    </section>
  );
}

const TOOL_TEXT: Record<string, (s: NextStep) => string> = {
  measure_voltage: (s) => `Voltage ${s.points[0]} to ${s.points[1]} (live)`,
  measure_resistance: (s) => `Resistance ${s.points[0]} to ${s.points[1]} (isolated)`,
  read_position_indicator: () => "Look at the position indicator",
  manual_operation_check: (s) => `Manual operation check, then resistance ${s.points[0]} to ${s.points[1]}`,
  isolate_sources: () => "Request isolation of both sources (approval)",
  submit_diagnosis: () => "Submit the diagnosis",
};

/** The planner's next step before it is taken: the probe points are outlined on the drawing, and each possible result
 * lists the causes it would keep. */
export function NextStepCard({ next, title = "Next step (planner)", note }: { next: NextStep; title?: string; note?: string }) {
  const text = (TOOL_TEXT[next.tool] ?? ((s: NextStep) => s.tool))(next);
  return (
    <section className="hyp-card next-step-card">
      <div className="card-title">
        <span>{title}</span>
        <span className="muted">
          {next.causes_left} root cause{next.causes_left === 1 ? "" : "s"} left
        </span>
      </div>
      <div className="next-what">{text}</div>
      <div className="muted next-why">{next.why}{next.gain_bits !== undefined && ` (${next.gain_bits} bits)`}</div>
      {next.outcomes.length > 0 && (
        <ul className="next-outcomes">
          {next.outcomes.map((o, i) => (
            <li key={i}>
              <span className="next-reading">if {o.reading}:</span>{" "}
              {o.causes.join(", ")}
              {o.n > o.causes.length && <em> and {o.n - o.causes.length} more</em>}
            </li>
          ))}
        </ul>
      )}
      {note && <div className="muted next-note">{note}</div>}
    </section>
  );
}

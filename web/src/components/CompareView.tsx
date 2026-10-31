import type { CompareColumn, CompareResult } from "../types";

const ORDER = [
  ["human", "Engineer"],
  ["agent", "Agent (Muse Spark)"],
  ["baseline", "Half-split baseline"],
] as const;

const ATS_ORDER = [
  ["human", "Engineer"],
  ["agent", "Agent (Muse Spark)"],
  ["hybrid", "Hybrid v2 (saved transcription)"],
  ["baseline", "Info-gain baseline (our redrawing)"],
] as const;

function Column({ title, col, pending }: { title: string; col?: CompareColumn; pending: string }) {
  if (!col) return <div className="cmp-col pending"><h3>{title}</h3><p className="muted">{pending}</p></div>;
  if (col.missing) return <div className="cmp-col"><h3>{title}</h3><p className="muted">{col.missing}</p></div>;
  if (col.error) return <div className="cmp-col"><h3>{title}</h3><p className="policy">{col.error}</p></div>;
  return (
    <div className="cmp-col">
      <h3>{title}</h3>
      {col.engineer && <div className="muted">{col.engineer}, recorded {col.recorded}</div>}
      {col.transcription && <div className="muted">{col.transcription}</div>}
      <span className={`verdict small v-${(col.verdict ?? "").replace(" ", "-")}`}>{col.verdict}</span>
      <div className="cmp-diag">{col.diagnosis}</div>
      {typeof col.confidence === "number" && <div className="muted">confidence {(col.confidence * 100).toFixed(0)}%</div>}
      <dl>
        <dt>measurements</dt><dd>{col.measurements}</dd>
        <dt>redundant</dt><dd>{col.redundant}</dd>
        <dt>blocked attempts</dt><dd>{col.blocked}</dd>
        <dt>approvals asked</dt><dd>{col.approvals}</dd>
        {col.strong_approvals !== undefined && (
          <>
            <dt>strong approvals asked</dt><dd>{col.strong_approvals}</dd>
            <dt>denied</dt><dd>{col.approvals_denied}</dd>
            <dt>approvals by</dt><dd>{col.approvals_by}</dd>
          </>
        )}
        <dt>time</dt><dd>{col.seconds?.toFixed(0)} s</dd>
        <dt>cost</dt><dd>${(col.cost_usd ?? 0).toFixed(3)}</dd>
      </dl>
      <ol className="sequence">
        {(col.sequence ?? []).map((s, i) => (
          <li key={i} className={s.startsWith("blocked") ? "blocked" : ""}>{s}</li>
        ))}
        {(col.sequence ?? []).length === 0 && <li className="muted">no meter readings</li>}
      </ol>
    </div>
  );
}

export function CompareView({ result, progress, onClose, ats = false }: { result: CompareResult | null; progress: { baseline: boolean; agentTurn: number; hybrid?: boolean } | null; onClose: () => void; ats?: boolean }) {
  const cols = result?.columns ?? {};
  const order = ats ? ATS_ORDER : ORDER;
  return (
    <div className="modal-backdrop">
      <div className="modal compare-modal" role="dialog" aria-label="Comparison">
        <div className="result-head">
          <div>
            <div className="modal-kicker">Same fault, {ats ? "four" : "three"} diagnosticians</div>
            <h2>{result ? result.fault : ats ? "Running the others on the same fault..." : "Running the agent and the baseline..."}</h2>
          </div>
          <button className="close" onClick={onClose} aria-label="Close comparison">{"×"}</button>
        </div>
        <div className="cmp-grid" style={{ gridTemplateColumns: `repeat(${order.length}, minmax(0, 1fr))` }}>
          {order.map(([key, title]) => (
            <Column
              key={key}
              title={title}
              col={cols[key]}
              pending={key === "agent" ? `running, turn ${progress?.agentTurn ?? 0}` : key === "baseline" ? (progress?.baseline ? "done" : "running")
                       : key === "hybrid" ? (progress?.hybrid ? "done" : "waiting") : ""}
            />
          ))}
        </div>
        {result && <p className="muted">{result.note}</p>}
      </div>
    </div>
  );
}

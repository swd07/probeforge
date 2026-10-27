import type { CompareColumn, CompareResult } from "../types";

const ORDER = [
  ["human", "Engineer"],
  ["agent", "Agent (Muse Spark)"],
  ["baseline", "Half-split baseline"],
] as const;

function Column({ title, col, pending }: { title: string; col?: CompareColumn; pending: string }) {
  if (!col) return <div className="cmp-col pending"><h3>{title}</h3><p className="muted">{pending}</p></div>;
  if (col.error) return <div className="cmp-col"><h3>{title}</h3><p className="policy">{col.error}</p></div>;
  return (
    <div className="cmp-col">
      <h3>{title}</h3>
      <span className={`verdict small v-${(col.verdict ?? "").replace(" ", "-")}`}>{col.verdict}</span>
      <div className="cmp-diag">{col.diagnosis}</div>
      {typeof col.confidence === "number" && <div className="muted">confidence {(col.confidence * 100).toFixed(0)}%</div>}
      <dl>
        <dt>measurements</dt><dd>{col.measurements}</dd>
        <dt>redundant</dt><dd>{col.redundant}</dd>
        <dt>blocked attempts</dt><dd>{col.blocked}</dd>
        <dt>approvals asked</dt><dd>{col.approvals}</dd>
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

export function CompareView({ result, progress, onClose }: { result: CompareResult | null; progress: { baseline: boolean; agentTurn: number } | null; onClose: () => void }) {
  const cols = result?.columns ?? {};
  return (
    <div className="modal-backdrop">
      <div className="modal compare-modal" role="dialog" aria-label="Comparison">
        <div className="result-head">
          <div>
            <div className="modal-kicker">Same fault, three diagnosticians</div>
            <h2>{result ? result.fault : "Running the agent and the baseline..."}</h2>
          </div>
          <button className="close" onClick={onClose} aria-label="Close comparison">{"×"}</button>
        </div>
        <div className="cmp-grid">
          {ORDER.map(([key, title]) => (
            <Column
              key={key}
              title={title}
              col={cols[key]}
              pending={key === "agent" ? `running, turn ${progress?.agentTurn ?? 0}` : key === "baseline" ? (progress?.baseline ? "done" : "running") : ""}
            />
          ))}
        </div>
        {result && <p className="muted">{result.note}</p>}
      </div>
    </div>
  );
}

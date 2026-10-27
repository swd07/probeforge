import type { ApprovalRequest, Done } from "../types";

export function ApprovalCard({ req, onAnswer }: { req: ApprovalRequest; onAnswer: (approve: boolean) => void }) {
  const what =
    req.tool === "set_power"
      ? "Re-apply power"
      : req.tool === "perform_action"
        ? `${String(req.args.action ?? "").replace("_", " ")} ${req.args.target ?? ""}`
        : req.tool;
  return (
    <div className="modal-backdrop">
      <div className="modal approval-modal" role="dialog" aria-label="Approval request">
        <div className="modal-kicker">Human approval required</div>
        <h2>{what}</h2>
        <p className="policy-reason">{req.policy_reason}</p>
        <div className="agent-reason">
          <span>Agent's reason</span>
          <p>{req.agent_reason}</p>
        </div>
        <div className="modal-actions">
          <button className="btn deny" onClick={() => onAnswer(false)}>
            Deny
          </button>
          <button className="btn approve" onClick={() => onAnswer(true)}>
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}

const VERDICT_TEXT: Record<string, string> = {
  correct: "Correct",
  justified: "Justified",
  wrong: "Wrong",
  "no diagnosis": "No diagnosis",
};

export function ResultCard({ done, showTruth, onToggleTruth, onClose }: { done: Done; showTruth: boolean; onToggleTruth: () => void; onClose: () => void }) {
  const d = done.diagnosis ?? {};
  const said =
    done.outcome === "diagnosed"
      ? `${d.component}${d.part ? " " + d.part : ""} ${d.failure_mode}`
      : done.outcome === "insufficient_information"
        ? "insufficient information"
        : done.outcome;
  return (
    <div className="result-card">
      <div className="result-head">
        <span className={`verdict v-${done.verdict.replace(" ", "-")}`}>{VERDICT_TEXT[done.verdict]}</span>
        <button className="close" onClick={onClose} aria-label="Hide result">
          ×
        </button>
      </div>
      <div className="reveal">
        <div>
          <span className="lbl">Injected fault</span>
          <span className="val fault">{done.fault}</span>
          {done.latent && <span className="tag">latent</span>}
        </div>
        <div>
          <span className="lbl">Agent diagnosis</span>
          <span className="val">{said}</span>
          {typeof d.confidence === "number" && <span className="tag">{(Number(d.confidence) * 100).toFixed(0)}%</span>}
        </div>
      </div>
      {done.twins.length > 0 && (
        <p className="twins">No tool can tell this fault apart from: {done.twins.join(", ")}.</p>
      )}
      <div className="figures">
        <div><b>{done.measurements}</b><span>measurements</span></div>
        <div><b>{done.redundant}</b><span>redundant</span></div>
        <div><b>{done.turns}</b><span>turns</span></div>
        <div><b>{(done.tokens / 1000).toFixed(0)}k</b><span>tokens</span></div>
        <div><b>${done.cost_usd.toFixed(3)}</b><span>cost</span></div>
        <div><b>{done.seconds.toFixed(0)} s</b><span>time</span></div>
        <div><b>{done.policy_blocked}</b><span>blocked</span></div>
        <div><b>{done.approvals}</b><span>approvals asked</span></div>
      </div>
      <button className="btn ghost" onClick={onToggleTruth}>
        {showTruth ? "Show the agent's measurements" : "Show true live wiring"}
      </button>
    </div>
  );
}

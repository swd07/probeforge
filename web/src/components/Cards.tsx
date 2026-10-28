import { useState } from "react";
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

interface ResultProps {
  done: Done;
  showTruth: boolean;
  onToggleTruth: () => void;
  saved?: string;
  onCompare?: () => void;
}

/** Docked at the top of the right panel so the schematic stays visible; collapses to one line. */
export function ResultCard({ done, showTruth, onToggleTruth, saved, onCompare }: ResultProps) {
  const [collapsed, setCollapsed] = useState(false);
  const manual = done.mode === "manual";
  const d = done.diagnosis ?? {};
  const said =
    done.outcome === "diagnosed"
      ? `${d.component}${d.part ? " " + d.part : ""} ${d.failure_mode}`
      : done.outcome === "insufficient_information"
        ? "insufficient information"
        : done.outcome;
  const dec = done.decisive;
  return (
    <section className={`result-card docked ${collapsed ? "collapsed" : ""}`}>
      <button className="result-head" onClick={() => setCollapsed((c) => !c)} aria-expanded={!collapsed}>
        <span className={`verdict v-${done.verdict.replace(" ", "-")}`}>{VERDICT_TEXT[done.verdict]}</span>
        <span className="head-fault">{done.fault}</span>
        <span className="chevron">{collapsed ? "▾" : "▴"}</span>
      </button>
      {!collapsed && (
        <div className="result-body">
          <div className="this-run">This run: {done.source}</div>
          <div className="reveal">
            <div>
              <span className="lbl">Injected fault</span>
              <span className="val fault">{done.fault}</span>
              {done.latent && <span className="tag">latent</span>}
            </div>
            <div>
              <span className="lbl">{manual ? "Your diagnosis" : "Agent diagnosis"}</span>
              <span className="val">{said}</span>
              {typeof d.confidence === "number" && <span className="tag">{(Number(d.confidence) * 100).toFixed(0)}%</span>}
            </div>
          </div>
          {dec && (
            <div className="decisive">
              <span className="lbl">Decisive {dec.meter ? "measurement" : "observation"} (step {dec.step})</span>
              <span className="dec-reading">{dec.reading}</span>
              {dec.healthy && <span className="dec-healthy">healthy panel: {dec.healthy}</span>}
              <span className="dec-move">
                winning hypothesis {(dec.before * 100).toFixed(0)}% {"→"} {(dec.after * 100).toFixed(0)}%
                {dec.shared_with > 0 && <em> (taken with {dec.shared_with} other observations before the update)</em>}
              </span>
            </div>
          )}
          {done.twins.length > 0 && <p className="twins">No tool can tell this fault apart from: {done.twins.join(", ")}.</p>}
          <div className="figures">
            <div><b>{done.measurements}</b><span>measurements</span></div>
            <div><b>{done.redundant}</b><span>redundant</span></div>
            {!manual && <div><b>{done.turns}</b><span>turns</span></div>}
            {!manual && <div><b>{(done.tokens / 1000).toFixed(0)}k</b><span>tokens</span></div>}
            {!manual && <div><b>${done.cost_usd.toFixed(3)}</b><span>cost</span></div>}
            <div><b>{done.seconds.toFixed(0)} s</b><span>time</span></div>
            <div><b>{done.policy_blocked}</b><span>blocked</span></div>
            <div><b>{done.approvals}</b><span>approvals</span></div>
          </div>
          {saved && <p className="muted saved">Trace saved: {saved}</p>}
          <div className="result-actions">
            <button className="btn ghost" onClick={onToggleTruth}>
              {showTruth ? "Show the measurements" : "Show true live wiring"}
            </button>
            {onCompare && (
              <button className="btn primary" onClick={onCompare}>
                Compare with agent and baseline
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

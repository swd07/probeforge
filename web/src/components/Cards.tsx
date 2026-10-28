import { useState } from "react";
import type { ApprovalRequest, Done, FlagsRequest, WiringRequest } from "../types";

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

/** Regions the schematic transcription is unsure about; the flagged terminals light up on the schematic. */
export function FlagsCard({ req, onAnswer }: { req: FlagsRequest; onAnswer: (accept: boolean) => void }) {
  return (
    <div className="modal-backdrop flags-backdrop">
      <div className="modal flags-modal" role="dialog" aria-label="Confirm the schematic read">
        <div className="modal-kicker">Human check of the schematic read</div>
        <h2>{req.flags.length} uncertain region{req.flags.length > 1 ? "s" : ""}</h2>
        <p className="policy-reason">
          Muse Spark transcribed the schematic and flagged these places. Check them on the drawing (highlighted) before the
          planner relies on the netlist.
        </p>
        <ul className="flag-list">
          {req.flags.map((f, i) => (
            <li key={i}>
              <span className="flag-terms">{f.terminals.join(", ")}</span>
              <span>{f.reason}</span>
            </li>
          ))}
        </ul>
        <div className="modal-actions">
          <button className="btn deny" onClick={() => onAnswer(false)}>
            Reject (stop)
          </button>
          <button className="btn approve" onClick={() => onAnswer(true)}>
            Confirm and diagnose
          </button>
        </div>
      </div>
    </div>
  );
}

export function WiringCard({ req, onChoose }: { req: WiringRequest; onChoose: (choice: number | null) => void }) {
  return (
    <div className="modal-backdrop flags-backdrop">
      <div className="modal flags-modal wiring-modal" role="dialog" aria-label="Confirm the wiring">
        <div className="modal-kicker">Human check of a flagged region</div>
        <h2>The answer depends on wiring the read was unsure of</h2>
        <p className="policy-reason">
          Several wirings of {req.region.join(", ")} fit every reading and point to different faults. Check this region on the
          real panel (highlighted on the drawing) and pick the wiring you find.
        </p>
        <ul className="flag-list">
          {req.options.map((o, i) => (
            <li key={i}>
              <button className="btn ghost wiring-option" onClick={() => onChoose(i)}>
                <b>{o.fault}</b> if the wiring is:
                <span className="flag-terms">{o.wiring.join("; ")}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="modal-actions">
          <button className="btn deny" onClick={() => onChoose(null)}>
            Cannot check now (report the pole as ambiguous)
          </button>
        </div>
      </div>
    </div>
  );
}

const VERDICT_TEXT: Record<string, string> = {
  correct: "Correct",
  justified: "Justified",
  "pole open": "Pole open",
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
  const hybrid = done.mode === "hybrid";
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
              <span className="lbl">{manual ? "Your diagnosis" : hybrid ? "Pipeline diagnosis" : "Agent diagnosis"}</span>
              <span className="val">{said}</span>
              {typeof d.confidence === "number" && <span className="tag">{(Number(d.confidence) * 100).toFixed(0)}%</span>}
            </div>
            {typeof d.note === "string" && d.note && (
              <div>
                <span className="lbl">Note</span>
                <span className="val">{d.note}</span>
              </div>
            )}
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
          {hybrid && done.explanation && (
            <div className="explanation">
              <span className="lbl">For the technician (Muse Spark)</span>
              <p>{done.explanation}</p>
            </div>
          )}
          {hybrid && (
            <div className="hybrid-facts">
              <div>
                Schematic read: {done.transcription}
                {done.transcription_wrong_nets !== undefined && (
                  <em> ({done.transcription_wrong_nets === 0 ? "all nets right" : `${done.transcription_wrong_nets} of the true nets read wrong`})</em>
                )}
              </div>
              <div>
                Netlist corrections during the run: {done.corrections?.filter((c) => !c.rejected).length ?? 0}
                {(done.corrections?.filter((c) => c.rejected).length ?? 0) > 0 && (
                  <em>, {done.corrections!.filter((c) => c.rejected).length} rejected (changed fault-free behaviour no reading contradicted)</em>
                )}
                {done.gave_up && <em>, no consistent netlist found: handed over to a human</em>}
              </div>
              {done.wiring_check && (
                <div>
                  Wiring check ({done.wiring_check.region.join(", ")}): {done.wiring_check.verdict}
                </div>
              )}
            </div>
          )}
          {done.twins.length > 0 && <p className="twins">No tool can tell this fault apart from: {done.twins.join(", ")}.</p>}
          <div className="figures">
            <div><b>{done.measurements}</b><span>measurements</span></div>
            <div><b>{done.redundant}</b><span>redundant</span></div>
            {!manual && <div><b>{done.turns}</b><span>{hybrid ? "model calls" : "turns"}</span></div>}
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

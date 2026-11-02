import { useState } from "react";
import { tidyExplanation } from "../explanationText";
import { errorText, explanationLabel } from "../runError";
import { idText, modeText, readable, sentence } from "../labels";
import type { ApprovalRequest, AtsPanel, Done, FlagsRequest, WiringRequest } from "../types";

/** ATS bench strong approval: the policy's own facts next to the requester's reason, the cited readings, and a second
 * explicit confirmation before the approval goes through. */
function StrongApprovalCard({ req, onAnswer, human, who }: { req: ApprovalRequest; onAnswer: (approve: boolean) => void; human: boolean; who?: string }) {
  const [checked, setChecked] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const what = requestTitle(req);
  return (
    <div className="modal-backdrop">
      <div className="modal approval-modal strong" role="dialog" aria-label="Strong approval request">
        <div className="modal-kicker strong">Strong approval required</div>
        <h2>{what}</h2>
        <p className="policy-reason">{readable(req.policy_reason)}</p>
        {(req.facts ?? []).map((f, i) => (
          <p key={i} className="policy-fact">
            Policy: {f}
          </p>
        ))}
        <div className="agent-reason">
          <span>{who ?? (human ? "Your reason" : "Agent's reason")}</span>
          <p>{req.agent_reason}</p>
        </div>
        <div className="evidence-list">
          <span>Cited readings</span>
          <ul>
            {(req.evidence ?? []).map((e) => (
              <li key={e.step}>
                #{e.step} {e.text}
              </li>
            ))}
          </ul>
        </div>
        <label className="check confirm-check">
          <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          I have checked the cited readings and the policy facts against the reason
        </label>
        <div className="modal-actions">
          <button className="btn deny" onClick={() => onAnswer(false)}>
            Deny
          </button>
          {!confirming ? (
            <button className="btn approve" disabled={!checked} onClick={() => setConfirming(true)}>
              Approve...
            </button>
          ) : (
            <button className="btn approve strong" onClick={() => onAnswer(true)}>
              Confirm approval (second confirmation)
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** The card title in sentence case: "Adjust cut-off contact TS:8-9", "Isolate sources". */
export function requestTitle(req: Pick<ApprovalRequest, "tool" | "args">): string {
  if (req.tool === "set_power") return "Re-apply power";
  const what = req.tool === "perform_action" ? `${idText(String(req.args.action ?? ""))} ${req.args.target ?? ""}`.trim() : idText(req.tool);
  return sentence(what);
}

export function ApprovalCard({ req, onAnswer, human = false, who }: { req: ApprovalRequest; onAnswer: (approve: boolean) => void; human?: boolean; who?: string }) {
  if (req.strong) return <StrongApprovalCard key={req.id} req={req} onAnswer={onAnswer} human={human} who={who} />;
  const what = requestTitle(req);
  return (
    <div className="modal-backdrop">
      <div className="modal approval-modal" role="dialog" aria-label="Approval request">
        <div className="modal-kicker">Human approval required</div>
        <h2>{what}</h2>
        <p className="policy-reason">{readable(req.policy_reason)}</p>
        {(req.facts ?? []).map((f, i) => (
          <p key={i} className="policy-fact">
            Policy: {f}
          </p>
        ))}
        {human && (
          <p className="muted">
            In engineer mode you play both roles: the technician who asks and the supervisor who approves. A real
            supervisor would check the reason before allowing it.
          </p>
        )}
        <div className="agent-reason">
          <span>{who ?? (human ? "Your reason" : "Agent's reason")}</span>
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
                <b>{modeText(o.fault)}</b> if the wiring is:
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
  compareLabel?: string;
  compareNote?: string; // the cost of the re-runs, on a line under the button
  atsPanel?: AtsPanel | null; // ATS: the live panel, for the critical load lost after the diagnosis
  defaultCollapsed?: boolean;
}

const mmss = (s: number) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.floor(Math.max(0, s) % 60)).padStart(2, "0")}`;

/** ATS: what the UPS countdown means for the outcome. A correct diagnosis made after the UPS ran out, or before a
 * repair the UPS did not last until, still lost the critical load. */
function UpsOutcome({ done, panel }: { done: Done; panel?: AtsPanel | null }) {
  const u = done.ups_at_diagnosis;
  if (!u) return null;
  const lostAfter = !u.load_lost && !!panel?.load_lost;
  const at = u.load_lost ? u.depleted_after_outage_s : panel?.ups.depleted_after_outage_s;
  const when = typeof at === "number" ? ` (UPS depleted ${mmss(at)} after the outage)` : "";
  const correct = done.verdict === "correct";
  return (
    <>
      <div className="ups-at-diag">
        <span className="lbl">UPS time left at diagnosis</span>
        <span className="val">{u.load_lost ? `0:00, critical load already lost${when}` : mmss(u.ups_left_s)}</span>
      </div>
      {(u.load_lost || lostAfter) && (
        <div className="load-lost">
          {correct
            ? `Diagnosis correct, but the UPS ran out before the ${u.load_lost ? "diagnosis" : "repair"}: critical load lost${when}.`
            : `Critical load lost: the UPS ran out before the ${u.load_lost ? "diagnosis" : "repair"}${when}.`}
        </div>
      )}
    </>
  );
}

/** Docked at the top of the right panel so the schematic stays visible; collapses to one line. */
/** The approval figures: approvals and, on the ATS bench, strong approvals as their own figure (a strong approval
 * is a second, explicit confirmation; one combined count would hide it). */
export function approvalFigures(done: { approvals: number; strong_approvals?: number }): { value: number; label: string }[] {
  const out = [{ value: done.approvals, label: "approvals" }];
  if (typeof done.strong_approvals === "number") out.push({ value: done.strong_approvals, label: "strong approvals" });
  return out;
}

/** The run's duration figure: real (wall-clock) time, which a viewer must not read as outage time (that is the UPS
 * clock on the ATS bench). */
export function timeFigure(seconds: number, pauseS?: number): { value: string; label: string; title: string } {
  return {
    value: `${seconds.toFixed(0)} s`,
    label: pauseS ? "wall clock (pauses excluded)" : "wall clock",
    title: `Real time the run took${pauseS ? `, excluding ${pauseS.toFixed(0)} s of UI display pauses` : ""}; outage time is the UPS clock`,
  };
}

export function ResultCard({ done, showTruth, onToggleTruth, saved, onCompare, compareLabel, compareNote, atsPanel, defaultCollapsed = false }: ResultProps) {
  const time = timeFigure(done.seconds, done.display_pause_s);
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const manual = done.mode === "manual";
  const hybrid = done.mode === "hybrid";
  const d = done.diagnosis ?? {};
  const stopped = done.outcome === "error" ? errorText(done.error) ?? "an error" : null;
  const said = stopped ? "no diagnosis" : done.diagnosis_text ? done.diagnosis_text : done.outcome === "diagnosed"
      ? `${d.component}${d.part ? " " + d.part : ""} ${d.failure_mode}`
      : done.outcome === "insufficient_information"
        ? "insufficient information"
        : done.outcome;
  const dec = done.decisive;
  return (
    <section className={`result-card docked ${collapsed ? "collapsed" : ""}`}>
      <button className="result-head" onClick={() => setCollapsed((c) => !c)} aria-expanded={!collapsed}>
        <span className={`verdict v-${done.verdict.replace(" ", "-")}`}>{VERDICT_TEXT[done.verdict]}</span>
        <span className="head-fault">{modeText(done.fault)}</span>
        <span className="chevron">{collapsed ? "▾" : "▴"}</span>
      </button>
      {!collapsed && (
        <div className="result-body">
          <div className="this-run">This run: {done.source}</div>
          <div className="reveal">
            <div>
              <span className="lbl">Injected fault</span>
              <span className="val fault">{modeText(done.fault)}</span>
              {done.latent && <span className="tag">latent</span>}
            </div>
            <div>
              <span className="lbl">{manual ? "Your diagnosis" : hybrid ? "Pipeline diagnosis" : "Agent diagnosis"}</span>
              <span className="val">{modeText(said)}</span>
              {typeof d.confidence === "number" && !done.twins_named && done.outcome === "diagnosed" && <span className="tag">{(Number(d.confidence) * 100).toFixed(0)}%</span>}
            </div>
            {typeof d.note === "string" && d.note && !done.twins_named && (
              <div>
                <span className="lbl">Note</span>
                <span className="val">{modeText(d.note)}</span>
              </div>
            )}
          </div>
          {stopped && <div className="run-error">The run stopped before a diagnosis: {stopped}.</div>}
          <UpsOutcome done={done} panel={atsPanel} />
          {/* the actions right under the verdict, so they stay in view when the card is taller than its half of the column */}
          <div className="result-actions">
            <button className="btn ghost" onClick={onToggleTruth}>
              {showTruth ? "Show the measurements" : "Show true live wiring"}
            </button>
            {onCompare && (
              <button className="btn primary" onClick={onCompare}>
                {compareLabel ?? "Compare with agent and baseline"}
              </button>
            )}
          </div>
          {onCompare && compareNote && <p className="muted compare-note">{compareNote}</p>}
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
              <span className="lbl">For the technician ({explanationLabel(done)})</span>
              <p>{tidyExplanation(done.explanation)}</p>
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
          {done.twins.length > 0 && <p className="twins">No tool can tell this fault apart from: {modeText(done.twins.join(", "))}.</p>}
          <div className="figures">
            <div><b>{done.measurements}</b><span>measurements</span></div>
            <div><b>{done.redundant}</b><span>redundant</span></div>
            {!manual && <div><b>{done.turns}</b><span>{hybrid ? "model calls" : "turns"}</span></div>}
            {!manual && <div><b>{(done.tokens / 1000).toFixed(0)}k</b><span>tokens</span></div>}
            {!manual && <div><b>${done.cost_usd.toFixed(3)}</b><span>cost</span></div>}
            <div title={time.title}>
              <b>{time.value}</b><span>{time.label}</span>
            </div>
            <div><b>{done.policy_blocked}</b><span>blocked</span></div>
            {approvalFigures(done).map((f) => <div key={f.label}><b>{f.value}</b><span>{f.label}</span></div>)}
          </div>
          {saved && <p className="muted saved">Trace saved: {saved}</p>}
        </div>
      )}
    </section>
  );
}

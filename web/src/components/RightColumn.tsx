import type { Dispatch, SetStateAction } from "react";
import type { AtsMeta, AtsPanel as AtsPanelState, FeedItem, Meta, Probe } from "../types";
import type { State } from "../useSession";
import { AtsTranscriptionCard, NextStepCard } from "./AtsHybrid";
import { AtsManualPanel } from "./AtsManualPanel";
import { ResultCard } from "./Cards";
import { Feed } from "./Feed";
import { Fold } from "./Fold";
import { Hypotheses } from "./Hypotheses";
import { ManualPanel, type MeterState } from "./ManualPanel";

const ATS_SCENARIO =
  "Scenario: the utility fails, the generator starts, and the transfer switch should move the critical load to " +
  "Emergency within seconds while the UPS carries it (10 min). Pick a fault and press Start.";

interface Props {
  state: State;
  cur: boolean;
  ats: boolean;
  hybrid: boolean;
  manual: boolean;
  manualRun: boolean;
  busy: boolean;
  meta: Meta | null;
  atsMeta: AtsMeta | null;
  atsPanel: AtsPanelState | null;
  atsDiagnosing: boolean;
  atsIntervention: boolean;
  manualActive: boolean;
  toolSteps: number;
  lastProbe: Probe | null;
  logItems: FeedItem[];
  meter: MeterState;
  setMeter: Dispatch<SetStateAction<MeterState>>;
  showTruth: boolean;
  setShowTruth: Dispatch<SetStateAction<boolean>>;
  onCompare: (() => void) | undefined;
  tool: (name: string, args: Record<string, unknown>) => void;
  setDiagnosing: Dispatch<SetStateAction<boolean>>;
  suggesting: boolean;
  setSuggesting: Dispatch<SetStateAction<boolean>>;
  suggest: () => void;
}

/** The docked right column: the result card and the instruments (each collapsed to one line), the cards of the
 * running mode, the top 3 hypotheses, and the step log, which always keeps at least half of the height. */
export function RightColumn({ state, cur, ats, hybrid, manual, manualRun, busy, meta, atsMeta, atsPanel, atsDiagnosing, atsIntervention, manualActive, toolSteps, lastProbe, logItems, meter, setMeter, showTruth, setShowTruth, onCompare, tool, setDiagnosing, suggesting, setSuggesting, suggest }: Props) {
  return (
    <aside className="right docked">
      <div className="right-top">
        {cur && state.done && (
          <ResultCard
            done={state.done}
            showTruth={showTruth}
            onToggleTruth={() => setShowTruth((v) => !v)}
            saved={manualRun ? state.saved : undefined}
            atsPanel={ats ? atsPanel : undefined}
            defaultCollapsed
            compareLabel={ats ? "Compare on this fault (agent re-run about $0.10; hybrid and baseline free)" : undefined}
            onCompare={onCompare}
          />
        )}
        {ats && (manual || atsIntervention) ? (
          <Fold title={atsIntervention ? "Authorized intervention: isolate, repair, restore" : "Your instruments: meter, actions, Diagnose"}>
            <AtsManualPanel
              meta={atsMeta}
              panel={atsPanel}
              meter={meter}
              setMeter={setMeter}
              lastProbe={cur ? lastProbe : null}
              feed={cur ? state.feed : []}
              diagnosing={atsDiagnosing}
              intervention={atsIntervention}
              started={cur && state.status !== "idle"}
              stopped={cur && state.status === "stopped"}
              onTool={tool}
              onDiagnose={() => setDiagnosing(true)}
            />
          </Fold>
        ) : manual ? (
          <Fold title="Your instruments: meter, buttons, Diagnose">
            <ManualPanel
              meta={meta}
              panel={state.panel}
              meter={meter}
              setMeter={setMeter}
              lastProbe={lastProbe}
              active={manualActive}
              started={state.mode === "manual" && state.status !== "idle"}
              done={state.mode === "manual" && state.status === "done"}
              stopped={state.mode === "manual" && state.status === "stopped"}
              steps={toolSteps}
              onTool={tool}
              onDiagnose={() => setDiagnosing(true)}
            />
          </Fold>
        ) : null}
        {ats && hybrid && cur && state.atsTranscription && (
          <Fold title="Drawing read by Muse Spark (saved transcription)">
            <AtsTranscriptionCard t={state.atsTranscription} check={state.modelCheck} />
          </Fold>
        )}
        {ats && hybrid && cur && state.nextStep && busy && <NextStepCard next={state.nextStep} />}
        {atsDiagnosing && (
          state.suggestion ? (
            <NextStepCard
              next={state.suggestion}
              title="Suggestion (planner on our redrawing)"
              note="Shadow mode: take it or ignore it. Computed from your own readings, never from the fault; this trace is marked assisted."
              onUse={
                state.suggestion.tool === "measure_voltage" || state.suggestion.tool === "measure_resistance"
                  ? () => setMeter((m) => ({ ...m, kind: state.suggestion!.tool === "measure_voltage" ? "V" : "R", a: state.suggestion!.points[0], b: state.suggestion!.points[1] }))
                  : undefined
              }
            />
          ) : (
            <button className="btn ghost suggest-btn" disabled={suggesting}
                    onClick={() => { setSuggesting(true); suggest(); }}
                    title="The info-gain planner replays your readings on our redrawing and proposes the next one">
              {suggesting ? "Computing the suggestion (simulating every candidate fault)..."
                          : `Suggest the next reading (planner, shadow mode${state.suggestions > 0 ? `, ${state.suggestions} shown` : ""})`}
            </button>
          )
        )}
        {!manual && (
          <Hypotheses
            hypotheses={state.hypotheses}
            previous={state.previous}
            limit={3}
            title={hybrid ? "Candidate faults (top 3)" : "Hypotheses (top 3)"}
            subtitle={hybrid ? "share of simulated candidates still consistent" : "updated after each measurement"}
          />
        )}
      </div>
      <div className="log-dock">
        <Feed items={logItems} manual={manual} running={manualActive}
              title={hybrid ? "Hybrid pipeline log" : manual ? "Your steps" : "Agent log"}
              idleText={ats ? ATS_SCENARIO : undefined} />
      </div>
    </aside>
  );
}

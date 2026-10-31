import { type ReactNode, useEffect, useMemo, useState } from "react";
import { AtsTranscriptionCard, NextStepCard } from "./components/AtsHybrid";
import { AtsManualPanel } from "./components/AtsManualPanel";
import { LimitsModal } from "./components/AtsPanel";
import { AtsStatusColumn } from "./components/AtsStatus";
import { ApprovalCard, FlagsCard, ResultCard, WiringCard } from "./components/Cards";
import { CompareView } from "./components/CompareView";
import { DiagnosisForm } from "./components/DiagnosisForm";
import { Feed } from "./components/Feed";
import { FrontPanel } from "./components/FrontPanel";
import { Hypotheses } from "./components/Hypotheses";
import { ManualPanel, type MeterState } from "./components/ManualPanel";
import { Schematic, type View } from "./components/Schematic";
import { TopBar } from "./components/TopBar";
import { TroubleshootingView } from "./components/Troubleshooting";
import type { AtsMeta, AtsPanel as AtsPanelState, Bench, Meta, Mode } from "./types";
import { useSession } from "./useSession";

// ATS drawing: open on the operator circuit and sensing (the right-hand region), about 1.6 times the whole-drawing fit
const ATS_HOME: View = { x: 620, y: 90, w: 1720, h: 740 };
const ATS_SCENARIO =
  "Scenario: the utility fails, the generator starts, and the transfer switch should move the critical load to " +
  "Emergency within seconds while the UPS carries it (10 min). Pick a fault and press Start.";

/** The diagnosed part (or the whole component for a device fault), to zoom to and outline after the diagnosis. */
function diagnosedPart(d: Record<string, unknown> | null): { component: string; part: string } | null {
  if (!d || typeof d.component !== "string") return null;
  return { component: d.component, part: typeof d.part === "string" ? d.part : "" };
}

/** A section that collapses to one line (closed by default); its content stays mounted, so its inputs keep state. */
function Fold({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <section className={`fold ${open ? "open" : ""}`}>
      <button className="fold-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>{title}</span>
        <span className="chevron">{open ? "\u25b4" : "\u25be"}</span>
      </button>
      <div className="fold-body" hidden={!open}>{children}</div>
    </section>
  );
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [svg, setSvg] = useState("");
  const [atsMeta, setAtsMeta] = useState<AtsMeta | null>(null);
  const [atsSvg, setAtsSvg] = useState("");
  const [bench, setBench] = useState<Bench>(() => (new URLSearchParams(location.search).get("bench") === "ats" ? "ats" : "star_delta"));
  const [pickNote, setPickNote] = useState("");
  const [showTruth, setShowTruth] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [limitsOpen, setLimitsOpen] = useState(false);
  const [meter, setMeter] = useState<MeterState>({ kind: "V", a: null, b: null, hold: 0.2, wait: 6, reason: "manual check" });
  const [chosenMode, setChosenMode] = useState<Mode>("agent");
  const ats = bench === "ats";
  const { state, start, answer, stop, tool, compare, confirmFlags, chooseWiring, suggest } = useSession(ats ? "NN" : meta?.neutral ?? "N");

  useEffect(() => {
    fetch("/api/meta").then((r) => r.json()).then(setMeta);
    fetch("/api/schematic").then((r) => r.text()).then(setSvg);
  }, []);

  useEffect(() => {
    if (!ats || atsMeta) return;
    fetch("/api/ats/meta").then((r) => r.json()).then(setAtsMeta);
    fetch("/api/ats/schematic").then((r) => r.text()).then(setAtsSvg);
  }, [ats, atsMeta]);

  useEffect(() => {
    if (!pickNote) return;
    const t = setTimeout(() => setPickNote(""), 2500);
    return () => clearTimeout(t);
  }, [pickNote]);

  useEffect(() => {
    if (state.status === "done") {
      setShowTruth(false);
      setDiagnosing(false);
    }
  }, [state.status]);

  useEffect(() => setSuggesting(false), [state.suggestions, state.error, state.status]);

  const [flashing, setFlashing] = useState(false);
  useEffect(() => {
    if (!state.flash) return;
    setFlashing(true);
    const t = setTimeout(() => setFlashing(false), 1200);
    return () => clearTimeout(t);
  }, [state.flash]);

  // the run's mode while it runs or after it finished; before Start (or after switching tabs) the chosen mode
  const busy = state.status === "running" || state.status === "approval";
  const view: Mode = busy || (state.status === "done" && state.mode === chosenMode) ? state.mode : chosenMode;
  const manual = view === "manual";
  const hybrid = view === "hybrid";
  const manualRun = state.mode === "manual"; // the finished run (result card, compare) was an engineer run
  const toolSteps = state.feed.filter((f) => f.kind === "tool").length;
  const flagged = state.flags ? state.flags.flags.flatMap((f) => f.terminals) : state.wiring ? state.wiring.region : [];
  const manualActive = manual && state.status === "running";
  const lastBlocked = [...state.feed].reverse().find((f) => f.kind === "tool" && f.ev.verdict === "block");
  const lastProbe = state.probes.length ? state.probes[state.probes.length - 1] : null;

  // the session on screen belongs to the chosen bench (switching the bench before Start shows an empty bench)
  const cur = state.bench === bench;
  const logItems = view === state.mode && cur ? state.feed : [];
  const curMeta = ats ? atsMeta : meta;
  const atsPanel = ats && cur ? (state.panel as unknown as AtsPanelState | null) : null;
  const atsDiagnosing = ats && cur && manual && state.mode === "manual" && state.status === "running" && !state.done;
  const atsIntervention = ats && cur && !!state.done?.intervention && state.status !== "stopped" && state.status !== "error";
  const checkedPosition = useMemo(() => {
    for (let i = state.feed.length - 1; i >= 0; i--) {
      const f = state.feed[i];
      if (f.kind === "tool" && f.ev.tool === "read_position_indicator" && f.ev.executed) {
        return `${String(f.ev.result.position_indicator)} at ${f.ev.result.time_s} s`;
      }
    }
    return null;
  }, [state.feed]);
  const suspects = useMemo(
    () => (ats && cur && state.status !== "idle" ? state.hypotheses.slice(0, 3).filter((h) => h.probability >= 0.1) : []).map((h) => ({
      component: h.component,
      part: h.part ?? "",
    })),
    [ats, cur, state.hypotheses, state.status],
  );

  const onCompare =
    cur && state.done && (manualRun || ats)
      ? () => {
          if (!state.compare) compare();
          setComparing(true);
        }
      : undefined;

  // first click sets probe A, second sets probe B; a third click starts a new pair. A = B is refused.
  const pick = (point: string) =>
    setMeter((m) => {
      if (m.a && !m.b && point === m.a) {
        setPickNote("Probe B must be a different point than A (A = B is refused).");
        return m;
      }
      return !m.a || (m.a && m.b) ? { ...m, a: point, b: null } : { ...m, b: point };
    });

  return (
    <div className={`app ${flashing ? "flash" : ""}`}>
      <TopBar meta={curMeta} state={state} mode={chosenMode} setMode={setChosenMode} bench={bench} setBench={setBench}
              onStart={(o) => start(o)} onStop={stop} onCompare={onCompare} onSheet={ats ? () => setSheetOpen(true) : undefined} />
      <main className={`layout ${ats ? "ats" : ""}`}>
        {ats && (
          <AtsStatusColumn meta={atsMeta} panel={atsPanel} checkedPosition={atsDiagnosing ? checkedPosition : undefined}
                           onLimits={() => setLimitsOpen(true)} />
        )}
        <div className="left">
          {!ats && (
            <FrontPanel
              meta={meta}
              panel={cur ? state.panel : null}
              pressed={state.pressed}
              onPress={manualActive ? (b) => tool("press_button", { button: b, hold_seconds: meter.hold }) : undefined}
              onPower={manualActive ? () => tool("set_power", { on: !state.panel?.power, reason: meter.reason }) : undefined}
            />
          )}
          <div className="schematic-wrap">
            <Schematic
              key={bench}
              svg={ats ? atsSvg : svg}
              nets={cur ? state.nets : {}}
              probes={cur ? state.probes : []}
              truthLive={cur && state.done && showTruth ? state.done.truth_live_nets : null}
              onPick={manualActive || atsIntervention ? pick : undefined}
              selected={manualActive || atsIntervention ? [meter.a, meter.b] : flagged}
              suspects={suspects}
              planned={ats && cur && busy ? (state.nextStep ?? state.suggestion)?.terminals ?? [] : []}
              followDefault={state.mode !== "manual"}
              fitKey={state.done ? "reveal" : state.feed.length === 0 ? "start" : "run"}
              home={ats ? ATS_HOME : undefined}
              focus={ats && cur && state.done?.outcome === "diagnosed" ? diagnosedPart(state.done.diagnosis) : null}
            />
            {pickNote && <div className="error-banner">{pickNote}</div>}
            {cur && state.error && <div className="error-banner">{state.error}</div>}
            {state.stage && state.status === "running" && <div className="stage-banner">{state.stage}</div>}
          </div>
        </div>
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
      </main>
      {flashing && lastBlocked && lastBlocked.kind === "tool" && (
        <div className="toast-blocked">Blocked by safety policy: {lastBlocked.ev.policy_reason}</div>
      )}
      {state.flags && <FlagsCard req={state.flags} onAnswer={(ok) => confirmFlags(state.flags!.id, ok)} />}
      {state.wiring && <WiringCard req={state.wiring} onChoose={(c) => chooseWiring(state.wiring!.id, c)} />}
      {state.approval && <ApprovalCard req={state.approval} human={manualRun} onAnswer={(ok) => answer(state.approval!.id, ok)} />}
      {diagnosing && curMeta && (
        <DiagnosisForm
          meta={curMeta}
          feed={state.feed}
          onCancel={() => setDiagnosing(false)}
          onSubmit={(args) => {
            tool("submit_diagnosis", args);
            setDiagnosing(false);
          }}
        />
      )}
      {sheetOpen && <TroubleshootingView onClose={() => setSheetOpen(false)} />}
      {limitsOpen && <LimitsModal meta={atsMeta} onClose={() => setLimitsOpen(false)} />}
      {comparing && <CompareView result={state.compare} progress={state.compareProgress} onClose={() => setComparing(false)} ats={ats} />}
    </div>
  );
}

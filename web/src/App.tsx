import { useEffect, useState } from "react";
import { ApprovalCard, FlagsCard, ResultCard } from "./components/Cards";
import { CompareView } from "./components/CompareView";
import { DiagnosisForm } from "./components/DiagnosisForm";
import { Feed } from "./components/Feed";
import { FrontPanel } from "./components/FrontPanel";
import { Hypotheses } from "./components/Hypotheses";
import { ManualPanel, type MeterState } from "./components/ManualPanel";
import { Schematic } from "./components/Schematic";
import { TopBar } from "./components/TopBar";
import type { Meta } from "./types";
import { useSession } from "./useSession";

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [svg, setSvg] = useState("");
  const [showTruth, setShowTruth] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [meter, setMeter] = useState<MeterState>({ kind: "V", a: null, b: null, hold: 0.2, wait: 6, reason: "manual check" });
  const { state, start, answer, stop, tool, compare, confirmFlags } = useSession(meta?.neutral ?? "N");

  useEffect(() => {
    fetch("/api/meta").then((r) => r.json()).then(setMeta);
    fetch("/api/schematic").then((r) => r.text()).then(setSvg);
  }, []);

  useEffect(() => {
    if (state.status === "done") {
      setShowTruth(false);
      setDiagnosing(false);
    }
  }, [state.status]);

  const [flashing, setFlashing] = useState(false);
  useEffect(() => {
    if (!state.flash) return;
    setFlashing(true);
    const t = setTimeout(() => setFlashing(false), 1200);
    return () => clearTimeout(t);
  }, [state.flash]);

  const manual = state.mode === "manual";
  const hybrid = state.mode === "hybrid";
  const flagged = state.flags ? state.flags.flags.flatMap((f) => f.terminals) : [];
  const manualActive = manual && state.status === "running";
  const lastBlocked = [...state.feed].reverse().find((f) => f.kind === "tool" && f.ev.verdict === "block");
  const lastProbe = state.probes.length ? state.probes[state.probes.length - 1] : null;

  // first click sets probe A, second sets probe B; a third click starts a new pair
  const pick = (point: string) =>
    setMeter((m) => (!m.a || (m.a && m.b) ? { ...m, a: point, b: null } : { ...m, b: point }));

  return (
    <div className={`app ${flashing ? "flash" : ""}`}>
      <TopBar meta={meta} state={state} onStart={(o) => start(o)} onStop={stop} />
      <main className="layout">
        <div className="left">
          <FrontPanel
            meta={meta}
            panel={state.panel}
            pressed={state.pressed}
            onPress={manualActive ? (b) => tool("press_button", { button: b, hold_seconds: meter.hold }) : undefined}
            onPower={manualActive ? () => tool("set_power", { on: !state.panel?.power, reason: meter.reason }) : undefined}
          />
          <div className="schematic-wrap">
            <Schematic
              svg={svg}
              nets={state.nets}
              probes={state.probes}
              truthLive={state.done && showTruth ? state.done.truth_live_nets : null}
              onPick={manualActive ? pick : undefined}
              selected={manualActive ? [meter.a, meter.b] : flagged}
              followDefault={!manual}
              fitKey={state.done ? "reveal" : state.feed.length === 0 ? "start" : "run"}
            />
            {state.error && <div className="error-banner">{state.error}</div>}
            {state.stage && state.status === "running" && <div className="stage-banner">{state.stage}</div>}
          </div>
        </div>
        <aside className="right">
          {state.done && (
            <ResultCard
              done={state.done}
              showTruth={showTruth}
              onToggleTruth={() => setShowTruth((v) => !v)}
              saved={manual ? state.saved : undefined}
              onCompare={
                manual
                  ? () => {
                      if (!state.compare) compare();
                      setComparing(true);
                    }
                  : undefined
              }
            />
          )}
          {manual ? (
            <ManualPanel
              meta={meta}
              panel={state.panel}
              meter={meter}
              setMeter={setMeter}
              lastProbe={lastProbe}
              active={manualActive}
              onTool={tool}
              onDiagnose={() => setDiagnosing(true)}
            />
          ) : (
            <Hypotheses
              hypotheses={state.hypotheses}
              previous={state.previous}
              title={hybrid ? "Candidate faults" : "Hypotheses"}
              subtitle={hybrid ? "share of simulated candidates still consistent" : "updated after each measurement"}
            />
          )}
          <Feed items={state.feed} manual={manual} title={hybrid ? "Hybrid pipeline" : undefined} />
        </aside>
      </main>
      {flashing && lastBlocked && lastBlocked.kind === "tool" && (
        <div className="toast-blocked">Blocked by safety policy: {lastBlocked.ev.policy_reason}</div>
      )}
      {state.flags && <FlagsCard req={state.flags} onAnswer={(ok) => confirmFlags(state.flags!.id, ok)} />}
      {state.approval && <ApprovalCard req={state.approval} onAnswer={(ok) => answer(state.approval!.id, ok)} />}
      {diagnosing && meta && (
        <DiagnosisForm
          meta={meta}
          feed={state.feed}
          onCancel={() => setDiagnosing(false)}
          onSubmit={(args) => {
            tool("submit_diagnosis", args);
            setDiagnosing(false);
          }}
        />
      )}
      {comparing && <CompareView result={state.compare} progress={state.compareProgress} onClose={() => setComparing(false)} />}
    </div>
  );
}

import { useEffect, useState } from "react";
import { ApprovalCard, ResultCard } from "./components/Cards";
import { Feed } from "./components/Feed";
import { FrontPanel } from "./components/FrontPanel";
import { Hypotheses } from "./components/Hypotheses";
import { Schematic } from "./components/Schematic";
import { TopBar } from "./components/TopBar";
import type { Meta } from "./types";
import { useSession } from "./useSession";

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [svg, setSvg] = useState("");
  const [showTruth, setShowTruth] = useState(false);
  const [showResult, setShowResult] = useState(true);
  const { state, start, answer, stop } = useSession(meta?.neutral ?? "N");

  useEffect(() => {
    fetch("/api/meta").then((r) => r.json()).then(setMeta);
    fetch("/api/schematic").then((r) => r.text()).then(setSvg);
  }, []);

  useEffect(() => {
    if (state.status === "done") {
      setShowTruth(false);
      setShowResult(true);
    }
  }, [state.status]);

  const [flashing, setFlashing] = useState(false);
  useEffect(() => {
    if (!state.flash) return;
    setFlashing(true);
    const t = setTimeout(() => setFlashing(false), 1200);
    return () => clearTimeout(t);
  }, [state.flash]);

  const lastBlocked = [...state.feed].reverse().find((f) => f.kind === "tool" && f.ev.verdict === "block");

  return (
    <div className={`app ${flashing ? "flash" : ""}`}>
      <TopBar meta={meta} state={state} onStart={(o) => start(o)} onStop={stop} />
      <main className="layout">
        <div className="left">
          <FrontPanel meta={meta} panel={state.panel} pressed={state.pressed} />
          <div className="schematic-wrap">
            <Schematic svg={svg} nets={state.nets} probes={state.probes} truthLive={state.done && showTruth ? state.done.truth_live_nets : null} />
            {state.done && showResult && (
              <ResultCard done={state.done} showTruth={showTruth} onToggleTruth={() => setShowTruth((v) => !v)} onClose={() => setShowResult(false)} />
            )}
            {state.status === "error" && <div className="error-banner">{state.error}</div>}
          </div>
        </div>
        <aside className="right">
          <Hypotheses hypotheses={state.hypotheses} previous={state.previous} />
          <Feed items={state.feed} />
        </aside>
      </main>
      {flashing && lastBlocked && lastBlocked.kind === "tool" && (
        <div className="toast-blocked">Blocked by safety policy: {lastBlocked.ev.policy_reason}</div>
      )}
      {state.approval && <ApprovalCard req={state.approval} onAnswer={(ok) => answer(state.approval!.id, ok)} />}
    </div>
  );
}

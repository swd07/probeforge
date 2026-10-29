import { useMemo, useState } from "react";
import type { FeedItem, Meta } from "../types";
import { describeTool } from "./Feed";

interface Evidence {
  step: number;
  type: "functional_test" | "instrument_reading";
  observation: string;
}

const FUNCTIONAL = new Set(["read_indicators", "press_button", "wait"]);
const INSTRUMENT = new Set(["measure_voltage", "measure_resistance"]);

/** Steps the engineer can cite, with the evidence type the policy will accept for each. */
function citable(feed: FeedItem[]): Evidence[] {
  const out: Evidence[] = [{ step: 0, type: "functional_test", observation: "panel at the start" }];
  for (const f of feed) {
    if (f.kind !== "tool" || !f.ev.executed) continue;
    const { title, detail } = describeTool(f.ev);
    const text = `${title}${detail ? ": " + detail : ""}`;
    if (INSTRUMENT.has(f.ev.tool) || (f.ev.tool === "press_button" && f.ev.probes.length > 0)) {
      out.push({ step: f.ev.step, type: "instrument_reading", observation: text });
    }
    if (FUNCTIONAL.has(f.ev.tool)) out.push({ step: f.ev.step, type: "functional_test", observation: text });
  }
  return out;
}

type Component = Meta["components"][number];

/** "whole device" only when the component has whole-device failure modes; otherwise its first part with modes. */
const defaultPart = (c: Component | undefined) => (!c || c.modes.length ? "" : c.parts.find((p) => p.modes.length)?.name ?? "");

export function DiagnosisForm({ meta, feed, onSubmit, onCancel }: { meta: Meta; feed: FeedItem[]; onSubmit: (args: Record<string, unknown>) => void; onCancel: () => void }) {
  const [outcome, setOutcome] = useState<"diagnosed" | "insufficient_information">("diagnosed");
  const [component, setComponent] = useState(meta.components[0]?.id ?? "");
  const [part, setPart] = useState(defaultPart(meta.components[0]));
  const [mode, setMode] = useState("");
  const [confidence, setConfidence] = useState(80);
  const options = useMemo(() => citable(feed), [feed]);
  const [chosen, setChosen] = useState<Set<number>>(new Set());

  const comp = meta.components.find((c) => c.id === component);
  const modes = part ? comp?.parts.find((p) => p.name === part)?.modes ?? [] : comp?.modes ?? [];
  const evidence = options.filter((_, i) => chosen.has(i));
  const valid = outcome === "insufficient_information" || (component && mode && evidence.length > 0);

  const submit = () =>
    onSubmit(
      outcome === "diagnosed"
        ? { outcome, component, part, failure_mode: mode, confidence: confidence / 100, evidence }
        : { outcome, confidence: confidence / 100, evidence },
    );

  return (
    <div className="modal-backdrop">
      <div className="modal diag-modal" role="dialog" aria-label="Submit diagnosis">
        <div className="modal-kicker">Submit diagnosis</div>
        <div className="segmented">
          <button className={outcome === "diagnosed" ? "on" : ""} onClick={() => setOutcome("diagnosed")}>
            Fault found
          </button>
          <button className={outcome === "insufficient_information" ? "on" : ""} onClick={() => setOutcome("insufficient_information")}>
            Insufficient information
          </button>
        </div>
        {outcome === "diagnosed" && (
          <div className="form-grid">
            <label>
              Component
              <select
                value={component}
                onChange={(e) => {
                  setComponent(e.target.value);
                  setPart(defaultPart(meta.components.find((c) => c.id === e.target.value)));
                  setMode("");
                }}
              >
                {meta.components.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} ({c.label})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Part
              <select
                value={part}
                onChange={(e) => {
                  setPart(e.target.value);
                  setMode("");
                }}
              >
                {(comp?.modes.length ?? 0) > 0 && <option value="">whole device</option>}
                {comp?.parts.filter((p) => p.modes.length).map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name} ({p.kind.replace("_", " ")})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Failure mode
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="">choose</option>
                {modes.map((m) => (
                  <option key={m} value={m}>
                    {m.replace("_", " ")}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        <label className="confidence">
          Confidence {confidence}%
          <input type="range" min={0} max={100} value={confidence} onChange={(e) => setConfidence(Number(e.target.value))} />
        </label>
        <div className="evidence">
          <span className="muted">Evidence (cite the steps that prove it)</span>
          <ul>
            {options.map((o, i) => (
              <li key={`${o.step}-${o.type}`}>
                <label>
                  <input
                    type="checkbox"
                    checked={chosen.has(i)}
                    onChange={(e) => {
                      const next = new Set(chosen);
                      if (e.target.checked) next.add(i);
                      else next.delete(i);
                      setChosen(next);
                    }}
                  />
                  <span className="step">#{o.step}</span>
                  <span className={`etype ${o.type}`}>{o.type === "instrument_reading" ? "meter" : "functional"}</span>
                  {o.observation}
                </label>
              </li>
            ))}
          </ul>
        </div>
        <div className="modal-actions">
          <button className="btn ghost" onClick={onCancel}>
            Back
          </button>
          <button className="btn approve" disabled={!valid} onClick={submit}>
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}

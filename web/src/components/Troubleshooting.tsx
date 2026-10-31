import { useEffect, useState } from "react";

interface Check {
  check: string;
  tool: string;
  tier: string;
  expected: Record<string, string>;
  separates: [string, string[]][][];
}

interface Sheet {
  family: string;
  variant: string;
  title: string;
  dev_cases: string[];
  symptom: { lights: string[]; display: string; alarms: string[]; generator: string; load_powered: boolean; metering: { Normal: number[]; Emergency: number[] }; events: string[] };
  causes: string[];
  checks: Check[];
  not_separated: string[][];
  not_separated_why: string[];
}

/** The troubleshooting sheet for families A and B (docs/ATS_TROUBLESHOOTING.md), generated from the simulator. */
export function TroubleshootingView({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<{ label: string; sheets: Sheet[] } | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState(0);
  useEffect(() => {
    fetch("/api/ats/troubleshooting")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);
  const s = data?.sheets[tab];
  const meas = s ? s.checks.filter((c) => Object.keys(c.expected).length > 0) : [];
  return (
    <div className="modal-backdrop">
      <div className="modal compare-modal sheet-modal" role="dialog" aria-label="Troubleshooting sheet">
        <div className="result-head">
          <div>
            <div className="modal-kicker">Troubleshooting sheet, ATS families A and B</div>
            <p className="sheet-label">{data?.label ?? "Generated from the simulator, not reviewed by an engineer."}</p>
          </div>
          <button className="close" onClick={onClose} aria-label="Close the troubleshooting sheet">{"×"}</button>
        </div>
        {error && <p className="policy">The sheet is not available: {error}</p>}
        {data && (
          <div className="segmented sheet-tabs" role="tablist">
            {data.sheets.map((x, i) => (
              <button key={x.variant} className={i === tab ? "on" : ""} onClick={() => setTab(i)}>
                {x.variant}
              </button>
            ))}
          </div>
        )}
        {s && (
          <div className="sheet-body">
            <h3>
              {s.variant}. Family {s.family}: {s.title}
            </h3>
            <div className="sheet-cols">
              <div>
                <h4>Symptom</h4>
                <ul>
                  <li>Lights on: {s.symptom.lights.join(", ") || "none"}</li>
                  <li>Display: {s.symptom.display}{s.symptom.alarms.length > 0 && `; alarm: ${s.symptom.alarms.join(", ")}`}</li>
                  <li>Generator {s.symptom.generator}; load {s.symptom.load_powered ? "powered" : "not powered (on UPS)"}</li>
                  <li>Metering: Normal {s.symptom.metering.Normal.join("/")} V, Emergency {s.symptom.metering.Emergency.join("/")} V</li>
                  <li>Events: {s.symptom.events.join("; ")}</li>
                </ul>
                <h4>Possible causes ({s.causes.length})</h4>
                <ol className="sheet-causes">
                  {s.causes.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ol>
              </div>
              <div>
                <h4>Checks in safe order</h4>
                <ol className="sheet-checks">
                  {s.checks.map((c, i) => (
                    <li key={i} className={c.tool === "isolate_sources" ? "isolate" : ""}>
                      <b>{c.check}</b> <span className="muted">({c.tier})</span>
                      {c.separates.map((g, k) => (
                        <div key={k} className="detail">
                          {g.map(([reading, causes], j) => (
                            <span key={j}>
                              {j > 0 && "; "}
                              <span className="next-reading">{reading}:</span>{" "}
                              {j === g.length - 1 && causes.length > 2 ? `the other ${causes.length}` : causes.join(", ")}
                            </span>
                          ))}
                        </div>
                      ))}
                    </li>
                  ))}
                </ol>
                {s.not_separated.length > 0 && (
                  <p className="muted">
                    No reading in the menu searched separates: {s.not_separated.map((g, i) => `${g.join(", ")} (${s.not_separated_why[i]})`).join("; ")}.
                  </p>
                )}
              </div>
            </div>
            <h4>Expected reading per cause</h4>
            <div className="sheet-table-wrap">
              <table className="quality sheet-table">
                <thead>
                  <tr>
                    <th>Cause</th>
                    {meas.map((c) => (
                      <th key={c.check}>{s.checks.indexOf(c) + 1}. {c.check}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {s.causes.map((cause) => (
                    <tr key={cause}>
                      <td>{cause}</td>
                      {meas.map((c) => (
                        <td key={c.check}>{c.expected[cause]}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">Dev cases with this symptom: {s.dev_cases.join(", ")}.</p>
          </div>
        )}
      </div>
    </div>
  );
}

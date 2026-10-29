import { useEffect, useRef } from "react";
import type { FeedItem, ToolEvent } from "../types";

const ICON: Record<string, string> = {
  read_indicators: "◉",
  press_button: "●",
  wait: "⏱",
  set_power: "⏻",
  measure_voltage: "V",
  measure_resistance: "Ω",
  get_schematic: "☷",
  perform_action: "⚒",
  submit_diagnosis: "✔",
};

export function describeTool(ev: ToolEvent): { title: string; detail: string } {
  const a = ev.args as Record<string, any>;
  const r = ev.result as Record<string, any>;
  switch (ev.tool) {
    case "measure_voltage":
      return { title: `Voltage ${a.point_a} → ${a.point_b}`, detail: r.volts !== undefined ? `${r.volts} V` : "" };
    case "measure_resistance":
      return { title: `Resistance ${a.point_a} → ${a.point_b}`, detail: r.ohms !== undefined ? (r.ohms === "open" ? "open" : `${r.ohms} Ω`) : "" };
    case "press_button": {
      const held = r.while_held?.motor;
      const after = r.after_release?.motor;
      const readings = (r.readings ?? []).map((x: any) => `${x.point_a}→${x.point_b} ${x.volts} V`).join(", ");
      return {
        title: `Press ${a.button}${a.hold_seconds && Number(a.hold_seconds) > 0.3 ? ` (hold ${a.hold_seconds} s)` : ""}`,
        detail: held !== undefined ? `while held: ${held}, after: ${after}${readings ? `; ${readings}` : ""}` : "",
      };
    }
    case "wait":
      return { title: `Wait ${a.seconds} s`, detail: r.motor ? `motor ${r.motor}` : "" };
    case "set_power":
      return { title: `Power ${a.on ? "on" : "off"}`, detail: a.reason ? `reason: ${a.reason}` : "" };
    case "read_indicators":
      return { title: "Read panel", detail: r.motor ? `motor ${r.motor}` : "" };
    case "get_schematic":
      return { title: "Read netlist", detail: "" };
    case "perform_action":
      return { title: `Request ${String(a.action).replace("_", " ")} ${a.target ?? ""}`, detail: a.reason ? `reason: ${a.reason}` : "" };
    case "submit_diagnosis":
      return {
        title: a.outcome === "insufficient_information" ? "Diagnosis: insufficient information" : `Diagnosis: ${a.component}${a.part ? " " + a.part : ""} ${a.failure_mode}`,
        detail: a.confidence !== undefined ? `confidence ${(Number(a.confidence) * 100).toFixed(0)}%` : "",
      };
    default:
      return { title: ev.tool, detail: "" };
  }
}

/** Model text is shown as written, except dashes used as punctuation (project style rule). */
const plain = (text: string) => text.replace(/\s*[\u2014\u2013]\s*/g, ", ");

export function Feed({ items, manual = false, title, running = false }: { items: FeedItem[]; manual?: boolean; title?: string; running?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // braces matter: newer browsers return a Promise from scrollIntoView, which React would call as cleanup
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items.length]);

  return (
    <section className="feed-card">
      <div className="card-title">
        <span>{title ?? (manual ? "Your steps" : "Agent reasoning")}</span>
        <span className="muted">every tool call passes the safety policy</span>
      </div>
      <div className="feed">
        {items.length === 0 && (
          <div className="muted empty">
            {manual && running
              ? "Your steps appear here, each checked by the safety policy (allowed, blocked, or waiting for approval)."
              : manual
                ? "Pick a fault and press Start. Your steps will appear here."
                : "Pick a fault and press Start."}
          </div>
        )}
        {items.map((it) => {
          if (it.kind === "thought") return <div key={it.id} className="item thought">{plain(it.text)}</div>;
          if (it.kind === "info") return <div key={it.id} className="item info">{it.text}</div>;
          if (it.kind === "transcription")
            return (
              <div key={it.id} className="item transcription">
                <div>
                  <b>Read:</b> {it.how}: {it.components} components, {it.nets} nets
                </div>
                {it.flags.length === 0 ? (
                  <div className="detail">no regions flagged as uncertain</div>
                ) : (
                  <div className="detail">
                    {it.flags.length} uncertain region{it.flags.length > 1 ? "s" : ""}
                    {it.accepted === undefined ? ", waiting for confirmation" : it.accepted ? ", confirmed by human" : ", rejected"}
                  </div>
                )}
              </div>
            );
          if (it.kind === "conflict")
            return (
              <div key={it.id} className="item conflict">
                <span className="step">#{it.step}</span> <b>Inconsistent reading:</b> {it.action}
                <div className="detail">real: {it.actual}</div>
                <div className="detail">no candidate fault of the transcribed netlist predicts this; asking Muse Spark to recheck the schematic</div>
              </div>
            );
          if (it.kind === "correction")
            return (
              <div key={it.id} className="item correction">
                <div>
                  <span className="step">#{it.step}</span> <b>Netlist correction</b> (planner rebuilt, readings replayed)
                </div>
                {it.explanation && <div className="detail">{plain(it.explanation)}</div>}
                <pre className="diff">
                  {it.diff.length === 0
                    ? "(no change)"
                    : it.diff.map((line, i) => (
                        <span key={i} className={line.startsWith("+") ? "add" : "del"}>
                          {line}
                          {"\n"}
                        </span>
                      ))}
                </pre>
              </div>
            );
          if (it.kind === "correction_rejected")
            return (
              <div key={it.id} className="item correction rejected">
                <div>
                  <span className="step">#{it.step}</span> <b>Netlist correction rejected</b> (it changes fault-free behaviour no reading contradicted)
                </div>
                <ul className="detail reasons">
                  {it.reasons.map((r, i) => (
                    <li key={i}>{plain(r)}</li>
                  ))}
                </ul>
                <pre className="diff">
                  {it.diff.map((line, i) => (
                    <span key={i} className={line.startsWith("+") ? "add" : "del"}>
                      {line}
                      {"\n"}
                    </span>
                  ))}
                </pre>
              </div>
            );
          if (it.kind === "wiring")
            return (
              <div key={it.id} className="item info wiring">
                {it.text}
              </div>
            );
          if (it.kind === "hypotheses")
            return (
              <div key={it.id} className="item hyp">
                <span className="step">#{it.step}</span> hypotheses updated
                {it.top && (
                  <span className="hyp-top">
                    {" "}lead: {it.top.component}
                    {it.top.part ? ` ${it.top.part}` : ""} {it.top.failure_mode} {(it.top.probability * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            );
          if (it.kind === "approval")
            return (
              <div key={it.id} className={`item approval ${it.approved === undefined ? "pending" : it.approved ? "granted" : "denied"}`}>
                <span className="step">#{it.req.step}</span> human approval requested: {it.req.policy_reason}
                <div className="detail">{manual ? "your reason" : "agent's reason"}: {it.req.agent_reason}</div>
                <div className="detail">{it.approved === undefined ? "waiting..." : it.approved ? "approved by human" : "denied by human"}</div>
              </div>
            );
          const ev = it.ev;
          const { title, detail } = describeTool(ev);
          const cls = ev.verdict === "block" ? "blocked" : ev.verdict === "needs_approval" ? "needs-approval" : ev.verdict === "error" ? "error" : "";
          return (
            <div key={it.id} className={`item tool ${cls} ${ev.tool}`}>
              <span className="icon">{ICON[ev.tool] ?? "•"}</span>
              <div className="body">
                <div>
                  <span className="step">#{ev.step}</span> {title}
                  {detail && <span className="detail-inline"> {detail}</span>}
                </div>
                {ev.verdict === "block" && <div className="policy">BLOCKED by safety policy: {ev.policy_reason}</div>}
                {ev.verdict === "error" && typeof ev.result.error === "string" && <div className="policy">{ev.result.error}</div>}
                {typeof ev.result.note === "string" && <div className="note">{ev.result.note}</div>}
              </div>
              <span className="t">{ev.sim_time_s.toFixed(1)} s</span>
            </div>
          );
        })}
        <div ref={end} />
      </div>
    </section>
  );
}

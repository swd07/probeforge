import { useEffect, useRef } from "react";
import type { FeedItem, Hypothesis, NextStep, ToolEvent } from "../types";

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
  read_panel: "◉",
  read_event_log: "☰",
  read_metering: "≋",
  read_position_indicator: "⇅",
  isolate_sources: "⏻",
  restore_sources: "⏻",
  manual_operation_check: "⇄",
  repeat_transfer_attempt: "↻",
};

const readingText = (x: any) => `${x.point_a}→${x.point_b} ${x.volts !== undefined ? `${x.volts} V` : x.ohms === "open" ? "open" : `${x.ohms} Ω`}`;

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
    case "read_panel":
      return { title: "Read controller panel", detail: r.display ? `${r.display}${r.load_lost && !r.load_powered ? ", critical load LOST (UPS depleted)" : r.load_powered ? ", load powered" : ", load on UPS"}` : "" };
    case "read_event_log":
      return { title: "Read event log", detail: r.events ? `${r.events.length} events` : "" };
    case "read_metering":
      return { title: "Read metering screen", detail: r.metering ? `N ${r.metering.Normal.join("/")} V, E ${r.metering.Emergency.join("/")} V` : "" };
    case "read_position_indicator":
      return { title: "Look at the position indicator", detail: r.position_indicator ? `mechanism on ${r.position_indicator}` : "" };
    case "isolate_sources":
      return { title: "Isolate both sources (52U open, generator locked out)", detail: a.reason ? `reason: ${a.reason}` : "" };
    case "restore_sources":
      return { title: "Restore sources", detail: a.reason ? `reason: ${a.reason}` : "" };
    case "manual_operation_check": {
      const rs = r.readings_at_other_position ?? r.readings ?? [];
      return {
        title: "Manual operation check (sources isolated)",
        detail: r.moved_to_other_position === undefined ? "" : `${r.moved_to_other_position ? "moved" : "did not move"}${rs.length ? "; at the other position " + rs.map(readingText).join(", ") : ""}`,
      };
    }
    case "repeat_transfer_attempt": {
      const rs = r.readings_during_command ?? [];
      const after = r["panel_after_10_s"];
      return {
        title: "Repeat transfer attempt",
        detail: after ? `${rs.length ? "during the command " + rs.map(readingText).join(", ") + "; " : ""}then: ${after.display}` : "",
      };
    }
    case "submit_diagnosis":
      if (typeof a.note === "string" && a.note.startsWith("no reading separates: ")) {
        const items = a.note.slice("no reading separates: ".length).split(", ").map((x: string) => x.trim().split(" "));
        const targets = new Set(items.map((x: string[]) => x[0]));
        return {
          title:
            targets.size === 1
              ? `Diagnosis: ${items[0][0].replace(":", " ")} ${items.map((x: string[]) => x[1]).join(" or ")}`
              : `Diagnosis: ${items.map((x: string[]) => x.join(" ").replace(":", " ")).join(" or ")}`,
          detail: targets.size === 1 ? "no reading separates them; same repair" : "no reading separates them",
        };
      }
      return {
        title: a.outcome === "insufficient_information" ? "Diagnosis: insufficient information" : `Diagnosis: ${a.component}${a.part ? " " + a.part : ""} ${a.failure_mode}`,
        detail: a.confidence !== undefined ? `confidence ${(Number(a.confidence) * 100).toFixed(0)}%` : "",
      };
    default:
      return { title: ev.tool, detail: "" };
  }
}

/** A tool entry with, for the hybrid, the plan that led to it and the leading cause after it. */
type Shown = FeedItem | { kind: "tool"; id: string; ev: ToolEvent; plan?: NextStep; lead?: Hypothesis | null };

/** Hybrid log, one entry per reading: a planned step, the reading it led to and the hypotheses update right after
 * become one entry (display only; approvals or notes in between stay as they are). A plan whose step has not come
 * yet is shown on its own, as the live "next" line. */
function compact(items: FeedItem[]): Shown[] {
  const out: Shown[] = [];
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    if (it.kind !== "plan") {
      out.push(it);
      continue;
    }
    let k = i + 1;
    while (k < items.length && k <= i + 3 && items[k].kind !== "tool") k++;
    const t = items[k];
    if (!t || t.kind !== "tool" || t.ev.tool !== it.next.tool) {
      out.push(it);
      continue;
    }
    out.push(...items.slice(i + 1, k));
    const h = items[k + 1];
    const lead = h && h.kind === "hypotheses" ? h.top : undefined;
    out.push({ ...t, plan: it.next, lead });
    i = h && h.kind === "hypotheses" ? k + 1 : k;
  }
  return out;
}

/** Model text is shown as written, except dashes used as punctuation (project style rule). */
const plain = (text: string) => text.replace(/\s*[\u2014\u2013]\s*/g, ", ");

export function Feed({ items, manual = false, title, running = false, idleText }: { items: FeedItem[]; manual?: boolean; title?: string; running?: boolean; idleText?: string }) {
  const box = useRef<HTMLDivElement>(null);
  const follow = useRef(true); // follow the newest entry unless the reader scrolled up
  useEffect(() => {
    const el = box.current;
    if (el && follow.current) el.scrollTop = el.scrollHeight;
  }, [items.length]);
  const shown = compact(items);
  const onScroll = () => {
    const el = box.current;
    if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  return (
    <section className="feed-card">
      <div className="card-title">
        <span>{title ?? (manual ? "Your steps" : "Agent reasoning")}</span>
        <span className="muted">every tool call passes the safety policy</span>
      </div>
      <div className="feed" ref={box} onScroll={onScroll}>
        {items.length === 0 && (
          <div className="muted empty">
            {manual && running
              ? "Your steps appear here, each checked by the safety policy (allowed, blocked, or waiting for approval)."
              : manual
                ? "Pick a fault and press Start. Your steps will appear here."
                : idleText ?? "Pick a fault and press Start."}
          </div>
        )}
        {shown.map((it) => {
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
          if (it.kind === "plan") {
            const n = it.next;
            const pts = n.points.length === 2 ? `${n.points[0]} → ${n.points[1]}` : n.points.join(", ");
            return (
              <div key={it.id} className="item plan">
                <span className="step">next</span> <b>Planned:</b> {n.tool.replace(/_/g, " ")} {pts}
                <div className="detail">
                  {n.why}
                  {n.gain_bits !== undefined && ` (${n.gain_bits.toFixed(2)} bits)`}; {n.causes_left} causes left
                </div>
              </div>
            );
          }
          if (it.kind === "explanation")
            return (
              <div key={it.id} className="item explanation-item">
                Explanation for the technician (Muse Spark): on the result card above
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
                <span className="step">#{it.req.step}</span> {it.req.strong ? "STRONG approval" : "human approval"} requested: {it.req.policy_reason}
                {it.req.facts?.map((f, i) => <div key={i} className="detail fact">policy: {f}</div>)}
                <div className="detail">{manual ? "your reason" : "agent's reason"}: {it.req.agent_reason}</div>
                <div className="detail">{it.approved === undefined ? "waiting..." : it.approved ? "approved by human" : "denied by human"}</div>
              </div>
            );
          const ev = it.ev;
          const { title, detail } = describeTool(ev);
          const cls = ev.verdict === "block" ? "blocked" : ev.verdict === "needs_approval" || ev.verdict === "needs_strong_approval" ? "needs-approval" : ev.verdict === "error" ? "error" : "";
          return (
            <div key={it.id} className={`item tool ${cls} ${ev.tool}`}>
              <span className="icon">{ICON[ev.tool] ?? "•"}</span>
              <div className="body">
                <div>
                  <span className="step">#{ev.step}</span> {title}
                  {detail && <span className="detail-inline"> {detail}</span>}
                </div>
                {ev.verdict === "block" && <div className="policy">BLOCKED by safety policy: {ev.policy_reason}</div>}
                {(ev.verdict === "error" || (!ev.executed && ev.verdict.startsWith("needs_"))) && typeof ev.result.error === "string" && (
                  <div className="policy">{ev.result.error}</div>
                )}
                {typeof ev.result.note === "string" && <div className="note">{ev.result.note}</div>}
                {"plan" in it && it.plan && it.plan.tool !== "submit_diagnosis" && (
                  <div className="detail planned-detail">
                    planned: {it.plan.why}
                    {it.plan.gain_bits !== undefined && ` (${it.plan.gain_bits.toFixed(2)} bits)`}, {it.plan.causes_left} causes
                    {it.lead && ` · lead after: ${it.lead.component}${it.lead.part ? " " + it.lead.part : ""} ${it.lead.failure_mode} ${(it.lead.probability * 100).toFixed(0)}%`}
                  </div>
                )}
              </div>
              <span className="t">{ev.sim_time_s.toFixed(1)} s</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

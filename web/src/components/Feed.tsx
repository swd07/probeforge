import { useEffect, useRef } from "react";
import type { FeedItem, Hypothesis, NextStep, ToolEvent } from "../types";
import { idText, modeText, readable } from "../labels";
import { ICON, describeTool, plain } from "./feedText";

export { describeTool } from "./feedText";

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
                <span className="step">next</span> <b>Planned:</b> {idText(n.tool)} {pts}
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
                    {it.top.part ? ` ${it.top.part}` : ""} {modeText(it.top.failure_mode)} {(it.top.probability * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            );
          if (it.kind === "approval")
            return (
              <div key={it.id} className={`item approval ${it.approved === undefined ? "pending" : it.approved ? "granted" : "denied"}`}>
                <span className="step">#{it.req.step}</span> {it.req.strong ? "STRONG approval" : "human approval"} requested: {readable(it.req.policy_reason)}
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
                {ev.verdict === "block" && <div className="policy">BLOCKED by safety policy: {readable(ev.policy_reason)}</div>}
                {(ev.verdict === "error" || (!ev.executed && ev.verdict.startsWith("needs_"))) && typeof ev.result.error === "string" && (
                  <div className="policy">{ev.result.error}</div>
                )}
                {typeof ev.result.note === "string" && <div className="note">{modeText(ev.result.note)}</div>}
                {"plan" in it && it.plan && it.plan.tool !== "submit_diagnosis" && (
                  <div className="detail planned-detail">
                    planned: {it.plan.why}
                    {it.plan.gain_bits !== undefined && ` (${it.plan.gain_bits.toFixed(2)} bits)`}, {it.plan.causes_left} causes
                    {it.lead && ` · lead after: ${it.lead.component}${it.lead.part ? " " + it.lead.part : ""} ${modeText(it.lead.failure_mode)} ${(it.lead.probability * 100).toFixed(0)}%`}
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

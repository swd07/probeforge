import { useEffect, useRef } from "react";
import type { NetState, Probe } from "../types";

interface Props {
  svg: string;
  nets: Record<string, NetState>;
  probes: Probe[];
  truthLive: string[] | null; // set after the run: the real live wiring
}

const SVG_NS = "http://www.w3.org/2000/svg";
const NET_CLASSES = ["net-live", "net-dead", "net-probed", "net-truth"];

function formatValue(p: Probe) {
  if (p.kind === "R") return p.value === "open" ? "open" : `${p.value} Ω`;
  return `${p.value} V`;
}

/** The schematic is the server-rendered SVG. Every wire carries data-net and every terminal data-terminal,
 * so the agent's probes and what it learned about each net are painted straight onto it. */
export function Schematic({ svg, nets, probes, truthLive }: Props) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = host.current?.querySelector("svg");
    if (!root) return;
    root.querySelectorAll(".probe-overlay").forEach((n) => n.remove());
    root.querySelectorAll("[data-net]").forEach((el) => el.classList.remove(...NET_CLASSES));
    root.querySelectorAll("circle[data-terminal]").forEach((el) => el.classList.remove("probe-active", "probe-old"));

    if (truthLive) {
      for (const net of truthLive) root.querySelectorAll(`[data-net="${CSS.escape(net)}"]`).forEach((el) => el.classList.add("net-truth"));
    } else {
      for (const [net, st] of Object.entries(nets)) {
        root.querySelectorAll(`[data-net="${CSS.escape(net)}"]`).forEach((el) => el.classList.add(`net-${st}`));
      }
    }

    const overlay = document.createElementNS(SVG_NS, "g");
    overlay.setAttribute("class", "probe-overlay");
    const lastStep = probes.length ? probes[probes.length - 1].step : -1;
    const recent = probes.slice(-4);
    for (const p of probes) {
      for (const t of [p.term_a, p.term_b]) {
        const c = root.querySelector(`circle[data-terminal="${CSS.escape(t)}"]`);
        c?.classList.add(p.step === lastStep ? "probe-active" : "probe-old");
      }
    }
    const placed: { x: number; y: number; w: number }[] = [];
    for (const p of [...recent].reverse()) {
      const c = root.querySelector(`circle[data-terminal="${CSS.escape(p.term_a)}"]`);
      if (!c) continue;
      const x = Number(c.getAttribute("cx"));
      let y = Number(c.getAttribute("cy"));
      const latest = p.step === lastStep;
      const label = `${formatValue(p)}  (${p.a}→${p.b})`;
      const g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("class", `reading ${latest ? "latest" : ""} ${p.kind === "R" ? "ohm" : "volt"}`);
      const w = 8 + label.length * 6.6;
      // newest label sits at its terminal; older ones move up until they do not overlap
      while (placed.some((q) => Math.abs(q.y - y) < 22 && x + 8 < q.x + 8 + q.w && q.x + 8 < x + 8 + w)) y -= 22;
      placed.push({ x, y, w });
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", String(x + 8));
      rect.setAttribute("y", String(y - 30));
      rect.setAttribute("width", String(w));
      rect.setAttribute("height", "20");
      rect.setAttribute("rx", "5");
      const text = document.createElementNS(SVG_NS, "text");
      text.setAttribute("x", String(x + 12));
      text.setAttribute("y", String(y - 16));
      text.textContent = label;
      const ring = document.createElementNS(SVG_NS, "circle");
      ring.setAttribute("cx", String(x));
      ring.setAttribute("cy", c.getAttribute("cy") ?? String(y));
      ring.setAttribute("r", latest ? "9" : "6");
      ring.setAttribute("class", "probe-ring");
      g.append(ring, rect, text);
      overlay.append(g);
    }
    root.append(overlay);
  }, [svg, nets, probes, truthLive]);

  return (
    <section className="schematic-card">
      <div className="card-title">
        <span>Schematic</span>
        <span className="legend">
          {truthLive ? (
            <>
              <i className="sw truth" /> live wiring (revealed)
            </>
          ) : (
            <>
              <i className="sw live" /> measured live <i className="sw dead" /> measured dead <i className="sw probed" /> probed
            </>
          )}
        </span>
      </div>
      <div className="schematic" ref={host} dangerouslySetInnerHTML={{ __html: svg }} />
    </section>
  );
}

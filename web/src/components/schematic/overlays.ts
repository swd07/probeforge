import type { Repaired } from "../../repairs";
import type { NetState, Probe } from "../../types";

const SVG_NS = "http://www.w3.org/2000/svg";
const NET_CLASSES = ["net-live", "net-dead", "net-probed", "net-truth"];
const SNAP_PX = 14; // a click this close to a terminal (screen pixels) picks the terminal

function formatValue(p: Probe) {
  if (p.kind === "R") return p.value === "open" ? "open" : `${p.value} Ω`;
  return `${p.value} V`;
}

export interface Marks {
  nets: Record<string, NetState>;
  probes: Probe[];
  truthLive: string[] | null;
  selected: (string | null)[];
  suspects: { component: string; part: string }[];
  planned: string[];
  repaired?: Repaired[];
}

/** The drawing's elements of a repaired part (a component prefix such as "CP:" selects all its parts). */
export function partElements(el: SVGSVGElement, part: string): SVGGraphicsElement[] {
  const sel = part.endsWith(":") ? `[data-part^="${CSS.escape(part)}"]` : `[data-part="${CSS.escape(part)}"]`;
  return Array.from(el.querySelectorAll<SVGGraphicsElement>(sel));
}

/** Paint what is known onto the server-rendered SVG (every wire carries data-net, every terminal data-terminal,
 * every part data-part): net states, picked points, suspects, probe points with reading labels, the planned reading. */
export function paint(el: SVGSVGElement, { nets, probes, truthLive, selected, suspects, planned, repaired = [] }: Marks): void {
  el.querySelectorAll(".probe-overlay").forEach((n) => n.remove());
  el.querySelectorAll("[data-net]").forEach((n) => n.classList.remove(...NET_CLASSES, "picked"));
  el.querySelectorAll("circle[data-terminal]").forEach((n) => n.classList.remove("probe-active", "probe-old", "picked", "planned"));
  el.querySelectorAll("[data-part].suspect").forEach((n) => n.classList.remove("suspect"));
  el.querySelectorAll("[data-part].repaired").forEach((n) => n.classList.remove("repaired"));
  for (const s of suspects) {
    const sel = s.part ? `[data-part="${CSS.escape(`${s.component}:${s.part}`)}"]` : `[data-part^="${CSS.escape(`${s.component}:`)}"]`;
    el.querySelectorAll(sel).forEach((n) => n.classList.add("suspect"));
  }
  for (const point of selected) {
    if (!point) continue;
    el.querySelectorAll(`[data-terminal="${CSS.escape(point)}"], [data-net="${CSS.escape(point)}"]`).forEach((n) => n.classList.add("picked"));
  }

  if (truthLive) {
    for (const net of truthLive) el.querySelectorAll(`[data-net="${CSS.escape(net)}"]`).forEach((n) => n.classList.add("net-truth"));
  } else {
    for (const [net, st] of Object.entries(nets)) {
      el.querySelectorAll(`[data-net="${CSS.escape(net)}"]`).forEach((n) => n.classList.add(`net-${st}`));
    }
  }

  const overlay = document.createElementNS(SVG_NS, "g");
  overlay.setAttribute("class", "probe-overlay");
  const lastStep = probes.length ? probes[probes.length - 1].step : -1;
  for (const p of probes) {
    for (const t of [p.term_a, p.term_b]) {
      el.querySelector(`circle[data-terminal="${CSS.escape(t)}"]`)?.classList.add(p.step === lastStep ? "probe-active" : "probe-old");
    }
  }
  const placed: { x: number; y: number; w: number }[] = [];
  for (const p of [...probes.slice(-4)].reverse()) {
    const c = el.querySelector(`circle[data-terminal="${CSS.escape(p.term_a)}"]`);
    if (!c) continue;
    const x = Number(c.getAttribute("cx"));
    let y = Number(c.getAttribute("cy"));
    const latest = p.step === lastStep;
    const label = `${formatValue(p)}  (${p.a}→${p.b})`;
    const w = 8 + label.length * 6.6;
    // newest label sits at its terminal; older ones move up until they do not overlap
    while (placed.some((q) => Math.abs(q.y - y) < 22 && x + 8 < q.x + 8 + q.w && q.x + 8 < x + 8 + w)) y -= 22;
    placed.push({ x, y, w });
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", `reading ${latest ? "latest" : ""} ${p.kind === "R" ? "ohm" : "volt"}`);
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
  const circles = planned.map((term) => el.querySelector(`circle[data-terminal="${CSS.escape(term)}"]`));
  const points = circles.map((c) => (c ? { x: Number(c.getAttribute("cx")), y: Number(c.getAttribute("cy")) } : null));
  const labels = plannedLabels(points);
  circles.forEach((c, i) => {
    const p = points[i], l = labels[i];
    if (!c || !p || !l) return;
    c.classList.add("planned");
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "planned-mark");
    const ring = document.createElementNS(SVG_NS, "circle");
    ring.setAttribute("cx", String(p.x));
    ring.setAttribute("cy", String(p.y));
    ring.setAttribute("r", "11");
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", String(l.x - l.w / 2));
    rect.setAttribute("y", String(l.y));
    rect.setAttribute("width", String(l.w));
    rect.setAttribute("height", String(PILL_H));
    rect.setAttribute("rx", "5");
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("x", String(l.x));
    text.setAttribute("y", String(l.y + PILL_H - 5));
    text.setAttribute("text-anchor", "middle");
    text.textContent = l.text;
    g.append(ring, rect, text);
    overlay.append(g);
  });
  // parts an approved repair has changed: outlined, with a pill centred under the part, below the terminal numbers
  // (above it are the component headings and the reading labels)
  for (const r of repaired) {
    const parts = partElements(el, r.part);
    if (!parts.length) continue;
    parts.forEach((n) => n.classList.add("repaired"));
    const boxes = parts.map((n) => n.getBBox());
    const mid = (Math.min(...boxes.map((b) => b.x)) + Math.max(...boxes.map((b) => b.x + b.width))) / 2;
    const top = Math.max(...boxes.map((b) => b.y + b.height)) + REPAIR_DY;
    const w = 12 + r.label.length * 7;
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "repaired-mark");
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", String(mid - w / 2));
    rect.setAttribute("y", String(top));
    rect.setAttribute("width", String(w));
    rect.setAttribute("height", String(PILL_H));
    rect.setAttribute("rx", "5");
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("x", String(mid));
    text.setAttribute("y", String(top + PILL_H - 5));
    text.setAttribute("text-anchor", "middle");
    text.textContent = r.label;
    g.append(rect, text);
    overlay.append(g);
  }
  el.append(overlay);
}

const PILL_H = 18;
const REPAIR_DY = 22; // under a repaired part's outline, clear of the terminal numbers
const LABEL_DY = 36; // below the terminal number, which the drawing puts about 20 to 33 px under the terminal

/** Where the "next A" / "next B" labels of a planned reading go: on an opaque pill centred under each terminal, one
 * row below the terminal's own number (the drawing writes terminal names above and numbers below, so labels at the
 * terminal covered them). A pill that would touch an earlier one drops a row. Null for a terminal not in the drawing. */
export function plannedLabels(points: ({ x: number; y: number } | null)[]): ({ x: number; y: number; w: number; text: string } | null)[] {
  const out: ({ x: number; y: number; w: number; text: string } | null)[] = [];
  points.forEach((p, i) => {
    if (!p) return out.push(null);
    const text = points.length > 1 ? `next ${i === 0 ? "A" : "B"}` : "next";
    const w = 10 + text.length * 7;
    let y = p.y + LABEL_DY;
    while (out.some((q) => q && Math.abs(q.y - y) < PILL_H + 2 && Math.abs(q.x - p.x) < (q.w + w) / 2 + 4)) y += PILL_H + 4;
    out.push({ x: p.x, y, w, text });
  });
  return out;
}

/** The terminal within a few screen pixels of a click (terminals are small), or null. */
export function nearestTerminal(el: SVGSVGElement, cx: number, cy: number): string | null {
  let best: string | null = null;
  let bestD = SNAP_PX;
  el.querySelectorAll("circle[data-terminal]").forEach((c) => {
    const r = c.getBoundingClientRect();
    const d = Math.hypot(r.x + r.width / 2 - cx, r.y + r.height / 2 - cy);
    if (d < bestD) {
      bestD = d;
      best = c.getAttribute("data-terminal");
    }
  });
  return best;
}

/** Drawing coordinates of these terminals (those found on the drawing). */
export function terminalPoints(el: SVGSVGElement, terminals: string[]): [number, number][] {
  return terminals
    .map((t) => el.querySelector(`circle[data-terminal="${CSS.escape(t)}"]`))
    .filter((c): c is Element => !!c)
    .map((c) => [Number(c.getAttribute("cx")), Number(c.getAttribute("cy"))]);
}

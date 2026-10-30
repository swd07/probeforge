import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { NetState, Probe } from "../types";

interface Props {
  svg: string;
  nets: Record<string, NetState>;
  probes: Probe[];
  truthLive: string[] | null; // set after the run: the real live wiring
  onPick?: (point: string) => void; // engineer mode: click a terminal or a wire to place a meter probe
  selected?: (string | null)[];
  suspects?: { component: string; part: string }[]; // ATS: the leading hypotheses, outlined on the drawing
  followDefault: boolean; // agent mode: zoom to each new measurement
  fitKey: string; // changes at session start and at the reveal: zoom out to the whole drawing
}

interface View {
  x: number;
  y: number;
  w: number;
  h: number;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const NET_CLASSES = ["net-live", "net-dead", "net-probed", "net-truth"];
const DRAG_PX = 4; // pointer movement below this is a click, above it a pan
const MIN_ZOOM_W = 240; // never zoom in further than this many drawing units across

function formatValue(p: Probe) {
  if (p.kind === "R") return p.value === "open" ? "open" : `${p.value} Ω`;
  return `${p.value} V`;
}

/** The schematic is the server-rendered SVG. Every wire carries data-net and every terminal data-terminal,
 * so probes and what was learned about each net are painted straight onto it. Zoom and pan work on the
 * viewBox, so labels stay sharp at any zoom. */
const SNAP_PX = 14; // a click this close to a terminal (screen pixels) picks the terminal

export function Schematic({ svg, nets, probes, truthLive, onPick, selected = [], suspects = [], followDefault, fitKey }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const full = useRef<View | null>(null);
  const view = useRef<View | null>(null);
  const anim = useRef<number>(0);
  const drag = useRef<{ x: number; y: number; start: View; moved: boolean } | null>(null);
  const [follow, setFollow] = useState(followDefault);

  useEffect(() => setFollow(followDefault), [followDefault]);

  const root = () => host.current?.querySelector("svg") ?? null;

  const apply = (v: View) => {
    view.current = v;
    root()?.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
  };

  /** Keep the box inside the drawing (with a margin) and at the container's aspect ratio. */
  const normalize = useCallback((v: View): View => {
    const f = full.current!;
    const rect = host.current!.getBoundingClientRect();
    const aspect = rect.height > 0 ? rect.width / rect.height : f.w / f.h;
    let { w, h } = v;
    if (w / h > aspect) h = w / aspect;
    else w = h * aspect;
    w = Math.min(Math.max(w, MIN_ZOOM_W), f.w * 1.6);
    h = w / aspect;
    const cx = Math.min(Math.max(v.x + v.w / 2, f.x), f.x + f.w);
    const cy = Math.min(Math.max(v.y + v.h / 2, f.y), f.y + f.h);
    return { x: cx - w / 2, y: cy - h / 2, w, h };
  }, []);

  const animateTo = useCallback((target: View, ms = 450) => {
    cancelAnimationFrame(anim.current);
    const from = view.current ?? target;
    const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      apply({
        x: from.x + (target.x - from.x) * e,
        y: from.y + (target.y - from.y) * e,
        w: from.w + (target.w - from.w) * e,
        h: from.h + (target.h - from.h) * e,
      });
      if (k < 1) anim.current = requestAnimationFrame(tick);
    };
    anim.current = requestAnimationFrame(tick);
  }, []);

  const fit = useCallback(() => {
    if (full.current) animateTo(full.current);
  }, [animateTo]);

  // remember the drawing's own viewBox once the SVG is in the DOM
  useEffect(() => {
    const el = root();
    if (!el) return;
    const vb = el.getAttribute("viewBox")?.split(/\s+/).map(Number);
    if (vb && vb.length === 4) {
      full.current = { x: vb[0], y: vb[1], w: vb[2], h: vb[3] };
      apply(full.current);
    }
  }, [svg]);

  useEffect(() => {
    fit();
  }, [fitKey, fit]);

  // mouse wheel zooms around the cursor (non-passive listener so the page does not scroll)
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!view.current || !full.current) return;
      e.preventDefault();
      cancelAnimationFrame(anim.current);
      setFollow(false);
      const svgEl = root()!;
      const pt = svgEl.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const p = pt.matrixTransform(svgEl.getScreenCTM()!.inverse());
      const k = Math.exp(e.deltaY * 0.0015);
      const v = view.current;
      apply(normalize({ x: p.x - (p.x - v.x) * k, y: p.y - (p.y - v.y) * k, w: v.w * k, h: v.h * k }));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [normalize]);

  const onPointerDown = (e: ReactPointerEvent) => {
    if (!view.current) return;
    drag.current = { x: e.clientX, y: e.clientY, start: view.current, moved: false };
  };
  const onPointerMove = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d || !host.current) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < DRAG_PX) return;
    if (!d.moved) {
      d.moved = true;
      cancelAnimationFrame(anim.current);
      setFollow(false);
      host.current.setPointerCapture(e.pointerId);
    }
    const rect = host.current.getBoundingClientRect();
    const scale = Math.max(d.start.w / rect.width, d.start.h / rect.height);
    apply({ ...d.start, x: d.start.x - dx * scale, y: d.start.y - dy * scale });
  };
  const onPointerUp = (e: ReactPointerEvent) => {
    if (drag.current?.moved && host.current?.hasPointerCapture(e.pointerId)) host.current.releasePointerCapture(e.pointerId);
    // keep the flag until the click event that follows this pointerup has been ignored
    setTimeout(() => (drag.current = null), 0);
  };

  const nearestTerminal = (cx: number, cy: number): string | null => {
    const el = root();
    if (!el) return null;
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
  };

  const click = (e: ReactMouseEvent) => {
    if (!onPick || drag.current?.moved) return; // a pan is not a click
    const target = e.target as Element;
    const terminal = target.closest("[data-terminal]");
    if (terminal) return onPick(terminal.getAttribute("data-terminal")!);
    // terminals are small: snap to the nearest one within a few pixels of the click before falling back to the wire
    const near = nearestTerminal(e.clientX, e.clientY);
    if (near) return onPick(near);
    const wire = target.closest("[data-net]");
    if (wire) onPick(wire.getAttribute("data-net")!);
  };

  // paint nets, probe points and reading labels
  useEffect(() => {
    const el = root();
    if (!el) return;
    el.querySelectorAll(".probe-overlay").forEach((n) => n.remove());
    el.querySelectorAll("[data-net]").forEach((n) => n.classList.remove(...NET_CLASSES, "picked"));
    el.querySelectorAll("circle[data-terminal]").forEach((n) => n.classList.remove("probe-active", "probe-old", "picked"));
    el.querySelectorAll("[data-part].suspect").forEach((n) => n.classList.remove("suspect"));
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
    el.append(overlay);
  }, [svg, nets, probes, truthLive, selected, suspects]);

  // agent mode: zoom to the area of the latest measurement
  const lastStep = probes.length ? probes[probes.length - 1].step : -1;
  useEffect(() => {
    if (!follow || lastStep < 0 || !full.current) return;
    const el = root();
    if (!el) return;
    const pts: [number, number][] = [];
    for (const p of probes.filter((q) => q.step === lastStep)) {
      for (const t of [p.term_a, p.term_b]) {
        const c = el.querySelector(`circle[data-terminal="${CSS.escape(t)}"]`);
        if (c) pts.push([Number(c.getAttribute("cx")), Number(c.getAttribute("cy"))]);
      }
    }
    if (!pts.length) return;
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    const y0 = Math.min(...ys);
    const y1 = Math.max(...ys);
    const w = Math.max(x1 - x0 + 360, 880);
    const h = Math.max(y1 - y0 + 240, 460);
    animateTo(normalize({ x: (x0 + x1) / 2 - w / 2, y: (y0 + y1) / 2 - h / 2 - 20, w, h }));
    // probes is read through lastStep on purpose: zoom only when a new measurement arrives
  }, [lastStep, follow, animateTo, normalize]); // eslint-disable-line react-hooks/exhaustive-deps

  const zoomBy = (k: number) => {
    const v = view.current;
    if (!v) return;
    setFollow(false);
    animateTo(normalize({ x: v.x + (v.w * (1 - k)) / 2, y: v.y + (v.h * (1 - k)) / 2, w: v.w * k, h: v.h * k }), 200);
  };

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
        <span className="zoom-controls">
          <label className="check" title="Zoom to each new measurement">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
            follow probes
          </label>
          <button onClick={() => zoomBy(1 / 1.4)} aria-label="Zoom in">+</button>
          <button onClick={() => zoomBy(1.4)} aria-label="Zoom out">{"−"}</button>
          <button
            onClick={() => {
              setFollow(false);
              fit();
            }}
          >
            Fit
          </button>
        </span>
      </div>
      <div
        className={`schematic ${onPick ? "pickable" : ""}`}
        ref={host}
        onClick={click}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <div className="zoom-hint muted">wheel to zoom, drag to pan</div>
    </section>
  );
}

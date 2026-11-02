import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import type { Repaired } from "../repairs";
import type { NetState, Probe } from "../types";
import { nearestTerminal, paint, partElements, terminalPoints } from "./schematic/overlays";
import { around, useViewBox, type View } from "./schematic/viewBox";

export type { View } from "./schematic/viewBox";

interface Props {
  svg: string;
  nets: Record<string, NetState>;
  probes: Probe[];
  truthLive: string[] | null; // set after the run: the real live wiring
  onPick?: (point: string) => void; // engineer mode: click a terminal or a wire to place a meter probe
  selected?: (string | null)[];
  suspects?: { component: string; part: string }[]; // ATS: the leading hypotheses, outlined on the drawing
  planned?: string[]; // ATS: terminals of the next planned reading (dashed rings, "next")
  runKey: number | null; // changes at every new run: "follow probes" turns back on (a manual zoom turns it off)
  fitKey: string; // changes at session start and at the reveal: zoom out to the home view
  home?: View; // the default view (drawing units); without it the home view is the whole drawing
  focus?: { component: string; part: string } | null;
  repaired?: Repaired[]; // ATS: parts an approved repair changed, outlined with a pill (follow on: the view goes there) // ATS: after the diagnosis, zoom to this part and outline it
}

/** The schematic is the server-rendered SVG. Every wire carries data-net and every terminal data-terminal,
 * so probes and what was learned about each net are painted straight onto it (schematic/overlays.ts). Zoom and pan
 * work on the viewBox (schematic/viewBox.ts), so labels stay sharp at any zoom. */
export function Schematic({ svg, nets, probes, truthLive, onPick, selected = [], suspects = [], planned = [], runKey, fitKey, home, focus = null, repaired = [] }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);

  useEffect(() => setFollow(true), [runKey]);

  const { root, full, normalize, inside, animateTo, fit, goHome, zoomBy, panned, pointer } = useViewBox(host, svg, home, () => setFollow(false));

  useEffect(() => {
    goHome();
  }, [fitKey, goHome]);

  // after a diagnosis: zoom to the diagnosed part (or the whole component for a device fault) and outline it;
  // declared after the home effect so it wins at the reveal. Not found on the drawing: the home view stays.
  const focusKey = focus ? `${focus.component}:${focus.part}` : "";
  useEffect(() => {
    const el = root();
    if (!el) return;
    el.querySelectorAll("[data-part].diagnosed").forEach((n) => n.classList.remove("diagnosed"));
    if (!focus || !full.current) return;
    const sel = focus.part ? `[data-part="${CSS.escape(focusKey)}"]` : `[data-part^="${CSS.escape(`${focus.component}:`)}"]`;
    const parts = Array.from(el.querySelectorAll<SVGGraphicsElement>(sel));
    if (!parts.length) return;
    parts.forEach((n) => n.classList.add("diagnosed"));
    const boxes = parts.map((n) => n.getBBox());
    const corners: [number, number][] = [
      [Math.min(...boxes.map((b) => b.x)), Math.min(...boxes.map((b) => b.y))],
      [Math.max(...boxes.map((b) => b.x + b.width)), Math.max(...boxes.map((b) => b.y + b.height))],
    ];
    animateTo(inside(normalize(around(corners, 300, 200, 620, 330, 0))));
    // focus is read through focusKey on purpose: zoom once per diagnosis
  }, [focusKey, svg, fitKey, animateTo, normalize, inside]); // eslint-disable-line react-hooks/exhaustive-deps

  const click = (e: ReactMouseEvent) => {
    if (!onPick || panned()) return; // a pan is not a click
    const target = e.target as Element;
    const terminal = target.closest("[data-terminal]");
    if (terminal) return onPick(terminal.getAttribute("data-terminal")!);
    // terminals are small: snap to the nearest one within a few pixels of the click before falling back to the wire
    const el = root();
    const near = el ? nearestTerminal(el, e.clientX, e.clientY) : null;
    if (near) return onPick(near);
    const wire = target.closest("[data-net]");
    if (wire) onPick(wire.getAttribute("data-net")!);
  };

  // paint nets, probe points and reading labels
  useEffect(() => {
    const el = root();
    if (el) paint(el, { nets, probes, truthLive, selected, suspects, planned, repaired });
  }, [svg, nets, probes, truthLive, selected, suspects, planned, repaired]); // eslint-disable-line react-hooks/exhaustive-deps

  // ATS intervention: with follow on, the view goes to a part as soon as its repair is done
  const lastRepair = repaired.length ? repaired[repaired.length - 1] : null;
  const repairKey = lastRepair ? `${lastRepair.step}:${lastRepair.part}` : "";
  useEffect(() => {
    if (!follow || !lastRepair || !full.current) return;
    const el = root();
    if (!el) return;
    const parts = partElements(el, lastRepair.part);
    if (!parts.length) return;
    const boxes = parts.map((n) => n.getBBox());
    const corners: [number, number][] = [
      [Math.min(...boxes.map((b) => b.x)), Math.min(...boxes.map((b) => b.y))],
      [Math.max(...boxes.map((b) => b.x + b.width)), Math.max(...boxes.map((b) => b.y + b.height))],
    ];
    animateTo(inside(normalize(around(corners, 300, 200, 620, 330, 0))));
    // repaired is read through repairKey on purpose: zoom once per repair
  }, [repairKey, follow, animateTo, normalize, inside]); // eslint-disable-line react-hooks/exhaustive-deps

  // agent mode: zoom to the area of the latest measurement
  const lastStep = probes.length ? probes[probes.length - 1].step : -1;
  useEffect(() => {
    if (!follow || lastStep < 0 || !full.current) return;
    const el = root();
    if (!el) return;
    const pts = terminalPoints(el, probes.filter((q) => q.step === lastStep).flatMap((p) => [p.term_a, p.term_b]));
    if (!pts.length) return;
    animateTo(inside(normalize(around(pts, 360, 240, 880, 460, 0))));
    // probes is read through lastStep on purpose: zoom only when a new measurement arrives
  }, [lastStep, follow, animateTo, normalize, inside]); // eslint-disable-line react-hooks/exhaustive-deps

  // ATS hybrid: with follow on, zoom to the next planned reading as soon as it is planned
  const plannedKey = planned.join("|");
  useEffect(() => {
    if (!follow || !planned.length || !full.current) return;
    const el = root();
    if (!el) return;
    const pts = terminalPoints(el, planned);
    if (!pts.length) return;
    animateTo(inside(normalize(around(pts, 360, 240, 880, 460, 0))));
    // planned is read through plannedKey on purpose: zoom only when the plan changes
  }, [plannedKey, follow, animateTo, normalize, inside]); // eslint-disable-line react-hooks/exhaustive-deps

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
          {home && (
            <button
              title="The default view"
              onClick={() => {
                setFollow(false);
                goHome();
              }}
            >
              Home
            </button>
          )}
          <button
            title="The whole drawing"
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
        {...pointer}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <div className="zoom-hint muted">wheel to zoom, drag to pan</div>
    </section>
  );
}

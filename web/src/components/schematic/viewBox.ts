import { type PointerEvent as ReactPointerEvent, type RefObject, useCallback, useEffect, useRef } from "react";

export interface View {
  x: number;
  y: number;
  w: number;
  h: number;
}

const DRAG_PX = 4; // pointer movement below this is a click, above it a pan
const MIN_ZOOM_W = 240; // never zoom in further than this many drawing units across

/** Zoom and pan of the drawing through its viewBox (labels stay sharp at any zoom): the drawing's own box, the home
 * view, animated moves, wheel zoom around the cursor and drag to pan. onManual is called when the user moves the view
 * (the caller turns follow mode off). */
export function useViewBox(host: RefObject<HTMLDivElement | null>, svg: string, home: View | undefined, onManual: () => void) {
  const full = useRef<View | null>(null);
  const view = useRef<View | null>(null);
  const anim = useRef<number>(0);
  const drag = useRef<{ x: number; y: number; start: View; moved: boolean } | null>(null);
  const manual = useRef(onManual);
  manual.current = onManual;

  const root = useCallback(() => host.current?.querySelector("svg") ?? null, [host]);

  const apply = useCallback((v: View) => {
    view.current = v;
    root()?.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
  }, [root]);

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
  }, [host]);

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
  }, [apply]);

  const fit = useCallback(() => {
    if (full.current) animateTo(full.current);
  }, [animateTo]);

  /** The home view at the container's aspect ratio, moved back inside the drawing vertically: a tall container must
   * not show an empty band above or below the drawing. */
  const homeView = useCallback((): View | null => {
    const f = full.current;
    if (!f || !home || !host.current) return f;
    const v = normalize(home);
    if (v.h > f.h) {
      // taller than the drawing: zoom in until the height fits, from the home region's left edge (the operator circuit)
      const w = (v.w * f.h) / v.h;
      return { x: home.x, y: f.y, w, h: f.h };
    }
    return { ...v, y: Math.min(Math.max(v.y, f.y), f.y + f.h - v.h) };
  }, [normalize, home, host]);

  const goHome = useCallback(() => {
    const v = homeView();
    if (v) animateTo(v);
  }, [animateTo, homeView]);

  // remember the drawing's own viewBox once the SVG is in the DOM
  useEffect(() => {
    const el = root();
    if (!el) return;
    const vb = el.getAttribute("viewBox")?.split(/\s+/).map(Number);
    if (vb && vb.length === 4) {
      full.current = { x: vb[0], y: vb[1], w: vb[2], h: vb[3] };
      apply(homeView() ?? full.current);
    }
  }, [svg]); // eslint-disable-line react-hooks/exhaustive-deps

  // mouse wheel zooms around the cursor (non-passive listener so the page does not scroll)
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!view.current || !full.current) return;
      e.preventDefault();
      cancelAnimationFrame(anim.current);
      manual.current();
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
  }, [normalize]); // eslint-disable-line react-hooks/exhaustive-deps

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
      manual.current();
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
  const panned = () => !!drag.current?.moved;

  const zoomBy = (k: number) => {
    const v = view.current;
    if (!v) return;
    manual.current();
    animateTo(normalize({ x: v.x + (v.w * (1 - k)) / 2, y: v.y + (v.h * (1 - k)) / 2, w: v.w * k, h: v.h * k }), 200);
  };

  return { root, full, normalize, animateTo, fit, goHome, zoomBy, panned, pointer: { onPointerDown, onPointerMove, onPointerUp } };
}

/** A view around these drawing points, at least minW x minH, slightly above centre (labels sit above terminals). */
export function around(pts: [number, number][], padW: number, padH: number, minW: number, minH: number, lift = 20): View {
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);
  const w = Math.max(x1 - x0 + padW, minW);
  const h = Math.max(y1 - y0 + padH, minH);
  return { x: (x0 + x1) / 2 - w / 2, y: (y0 + y1) / 2 - h / 2 - lift, w, h };
}

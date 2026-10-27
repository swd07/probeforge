import { useEffect, useState } from "react";
import type { Meta, Panel } from "../types";

const LAMP_COLOR: Record<string, string> = { Power: "white", Fault: "red", Forward: "green", Reverse: "amber" };

function Motor({ state }: { state: string }) {
  const running = /^(star|delta|unbalanced)_/.test(state);
  const reverse = state.endsWith("_reverse");
  const cls = state === "humming" ? "hum" : running ? (state.startsWith("delta") ? "spin-fast" : "spin-slow") : "";
  return (
    <div className="motor">
      <svg viewBox="0 0 60 60" className={`rotor ${cls} ${reverse ? "rev" : ""}`} aria-hidden>
        <circle cx="30" cy="30" r="26" className="stator" />
        <path d="M30 8 L34 30 L30 52 L26 30 Z" className="blade" />
        <path d="M8 30 L30 26 L52 30 L30 34 Z" className="blade" />
        <circle cx="30" cy="30" r="5" className="hub" />
      </svg>
      <div className="motor-text">
        <div className="motor-state">{state.replace("_", " ")}</div>
        <div className="motor-label">M1 motor</div>
      </div>
    </div>
  );
}

export function FrontPanel({ meta, panel, pressed }: { meta: Meta | null; panel: Panel | null; pressed: { button: string; at: number } | null }) {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    if (!pressed) return;
    setActive(pressed.button);
    const t = setTimeout(() => setActive(null), 900);
    return () => clearTimeout(t);
  }, [pressed]);

  const amps = panel?.line_currents_a ?? { U: 0, V: 0, W: 0 };
  return (
    <section className="front-panel">
      <div className="plate">
        <div className="lamps">
          {meta?.lamps.map((l) => (
            <div key={l.id} className="lamp-wrap">
              <div className={`lamp ${LAMP_COLOR[l.label] ?? "white"} ${panel?.lamps[l.label] ? "on" : ""}`} />
              <span>{l.label}</span>
            </div>
          ))}
        </div>
        <div className="buttons">
          {meta?.buttons.map((b) => (
            <div key={b.id} className="pb-wrap">
              <div className={`pushbutton ${b.label.startsWith("Stop") ? "red" : "green"} ${active === b.id ? "pressed" : ""}`} />
              <span>{b.label}</span>
            </div>
          ))}
        </div>
        <div className={`breaker ${panel?.power ? "on" : "off"}`}>
          <div className="breaker-handle" />
          <span>QF1 {panel?.power ? "ON" : "OFF"}</span>
        </div>
        <Motor state={panel?.motor ?? "stopped"} />
        <div className="ammeters">
          {Object.entries(amps).map(([line, a]) => (
            <div key={line} className="ammeter">
              <span className="line">{line}</span>
              <div className="amp-track">
                <div className={`amp-bar ${panel?.line_currents[line] ?? ""}`} style={{ width: `${Math.min(100, (a / 25) * 100)}%` }} />
              </div>
              <span className="amp-val">{a.toFixed(1)} A</span>
            </div>
          ))}
        </div>
        <div className="simtime">t = {panel?.time_s.toFixed(1) ?? "0.0"} s</div>
      </div>
    </section>
  );
}

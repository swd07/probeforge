import { idText, modeText } from "../labels";
import type { ToolEvent } from "../types";

// What the log shows for a tool call (also the readings list of the Engineer panel and the diagnosis form).
export const ICON: Record<string, string> = {
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

export const readingText = (x: any) => `${x.point_a}→${x.point_b} ${x.volts !== undefined ? `${x.volts} V` : x.ohms === "open" ? "open" : `${x.ohms} Ω`}`;

export function describeTool(ev: ToolEvent): { title: string; detail: string } {
  const { title, detail } = describeRaw(ev);
  return { title: modeText(title), detail: modeText(detail) };
}

function describeRaw(ev: ToolEvent): { title: string; detail: string } {
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
      return { title: `Request ${idText(String(a.action))} ${a.target ?? ""}`, detail: a.reason ? `reason: ${a.reason}` : "" };
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

/** Model text is shown as written, except dashes used as punctuation (project style rule). */
export const plain = (text: string) => text.replace(/\s*[\u2014\u2013]\s*/g, ", ");

import type { FeedItem } from "./types";

export interface Repaired {
  part: string; // a data-part id on the drawing ("TS:8-9"), or a component prefix ("CP:") for a controller replacement
  label: string; // the pill on the drawing: adjusted, replaced or repaired
  step: number;
}

/** "adjust_cutoff_contact" -> "adjusted", "replace_coil" -> "replaced", "repair_wire" -> "repaired". */
export function repairLabel(action: string): string {
  return action.startsWith("adjust") ? "adjusted" : action.startsWith("replace") ? "replaced" : "repaired";
}

/** The parts an authorized repair has actually changed, in order: executed repair steps only (approved and done),
 * never a request still waiting or a denied one. A part repaired twice keeps its latest step. */
export function repairedParts(feed: FeedItem[]): Repaired[] {
  const out = new Map<string, Repaired>();
  for (const f of feed) {
    if (f.kind !== "tool" || f.ev.tool !== "perform_action" || !f.ev.executed || f.ev.result?.done !== true) continue;
    const action = String(f.ev.args.action ?? "");
    const part = action === "replace_controller" ? "CP:" : String(f.ev.args.target ?? "").trim();
    if (!part) continue;
    out.delete(part);
    out.set(part, { part, label: repairLabel(action), step: f.ev.step });
  }
  return [...out.values()];
}

/** Readable labels for the ids the tools, the policy and the planner send (D53). Display only: the run records, the
 * policy and the frozen modules keep the ids. One spelling on screen: "cut-off". */

const ID_TEXT: Record<string, string> = {
  read_position_indicator: "look at the position indicator",
  get_schematic: "read the netlist",
  update_hypotheses: "record hypotheses",
  measure_voltage: "measure voltage",
  measure_resistance: "measure resistance",
  repeat_transfer_attempt: "repeat transfer attempt",
};

/** An action or tool id as words: "adjust_cutoff_contact" -> "adjust cut-off contact". */
export function idText(id: string): string {
  return ID_TEXT[id] ?? id.replace(/_/g, " ").replace(/\bcutoff\b/g, "cut-off");
}

// ids are lowercase words joined by underscores; part ids (W12_TS1-W12_P12) have capitals and digits and never match
const ID = /\b[a-z]+(?:_[a-z]+)+\b/g;

/** A policy reason or tool message with every id in it as words. */
export function readable(text: string): string {
  return text.replace(ID, (id) => idText(id));
}

/** The ids in a policy table cell, each followed by its label (the "Agent action limits" table keeps the agent's
 * vocabulary visible). */
export function labelIds(text: string): { text: string; label?: string }[] {
  const out: { text: string; label?: string }[] = [];
  let last = 0;
  for (const m of text.matchAll(ID)) {
    if (m.index! > last) out.push({ text: text.slice(last, m.index) });
    out.push({ text: m[0], label: idText(m[0]) });
    last = m.index! + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}

/** Sentence case: the first letter capitalized, the rest as written (card titles). */
export function sentence(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

const KIND_TEXT: Record<string, string> = {
  cutoff_n: "cut-off contact, closed on Normal",
  cutoff_e: "cut-off contact, closed on Emergency",
  main_n: "main contact, Normal",
  main_e: "main contact, Emergency",
  aux_n: "auxiliary contact, Normal",
  aux_e: "auxiliary contact, Emergency",
  contact_no: "NO contact",
  contact_nc: "NC contact",
};

/** A part kind as words, for the diagnosis form. */
export function kindText(kind: string): string {
  return KIND_TEXT[kind] ?? kind.replace(/_/g, " ");
}

/** Failure modes as words in a fault or cause text: "TS 8-9 stuck_closed" -> "TS 8-9 stuck closed". Only the
 * two-word modes are changed, so part ids keep their underscores. */
export function modeText(text: string): string {
  return text.replace(/\bstuck_(open|closed)\b/g, "stuck $1");
}

/** Under the ATS drawing's header in every view, whatever the zoom (the drawing's own title can be outside it). */
export const DRAWING_NOTE = "Our redrawing of ASCO wiring diagram 978741, not the official drawing.";

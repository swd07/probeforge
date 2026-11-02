import { describe, expect, it } from "vitest";
import { requestTitle } from "./components/Cards";
import { describeTool } from "./components/feedText";
import { DRAWING_NOTE, idText, kindText, labelIds, modeText, readable, reasonLabel } from "./labels";
import type { ToolEvent } from "./types";

const REPAIRS = ["replace_coil", "repair_wire", "repair_connector", "replace_cutoff_contact", "adjust_cutoff_contact", "replace_controller"];

// strings recorded in the dev-07 Engineer walkthrough (2026-11-02)
describe("no ids or underscores in the repair wording", () => {
  it("policy reasons", () => {
    expect(readable("adjust_cutoff_contact needs human approval")).toBe("adjust cut-off contact needs human approval");
    expect(readable("replace_coil needs human approval")).toBe("replace coil needs human approval");
    expect(readable("resistance measurement only with both sources isolated and locked out; call isolate_sources first"))
      .toBe("resistance measurement only with both sources isolated and locked out; call isolate sources first");
    const plain = "isolating both sources (lockout / tagout) needs human approval";
    expect(readable(plain)).toBe(plain);
  });

  it("card titles in sentence case", () => {
    expect(requestTitle({ tool: "perform_action", args: { action: "adjust_cutoff_contact", target: "TS:8-9" } })).toBe("Adjust cut-off contact TS:8-9");
    expect(requestTitle({ tool: "perform_action", args: { action: "replace_coil", target: "TS:A-B" } })).toBe("Replace coil TS:A-B");
    expect(requestTitle({ tool: "isolate_sources", args: {} })).toBe("Isolate sources");
    expect(requestTitle({ tool: "manual_operation_check", args: {} })).toBe("Manual operation check");
    expect(requestTitle({ tool: "restore_sources", args: {} })).toBe("Restore sources");
  });

  it("the feed line of a repair", () => {
    const ev = { tool: "perform_action", args: { action: "adjust_cutoff_contact", target: "TS:8-9", reason: "why" }, result: { done: true } } as unknown as ToolEvent;
    expect(describeTool(ev).title).toBe("Request adjust cut-off contact TS:8-9");
  });

  it("every repair label, one spelling", () => {
    for (const a of REPAIRS) {
      expect(idText(a)).not.toMatch(/_|cutoff/);
    }
    expect(idText("replace_cutoff_contact")).toBe("replace cut-off contact");
  });

  it("leaves part ids alone", () => {
    expect(readable("repair_wire H1:W12_TS1-W12_P12")).toBe("repair wire H1:W12_TS1-W12_P12");
  });

  it("part kinds in the diagnosis form", () => {
    expect(kindText("cutoff_n")).toBe("cut-off contact, closed on Normal");
    expect(kindText("solenoid")).toBe("solenoid");
  });
});

describe("Agent action limits keep the ids, with a label", () => {
  it("splits a table cell into ids and text", () => {
    expect(labelIds("isolate_sources (open 52U, lock out the generator)")).toEqual([
      { text: "isolate_sources", label: "isolate sources" },
      { text: " (open 52U, lock out the generator)" },
    ]);
    expect(labelIds("the same replacement again")).toEqual([{ text: "the same replacement again" }]);
  });
});

// strings recorded in the walkthrough: the suggestion card, the result card and the feed
describe("failure modes shown as words", () => {
  it("fault and cause texts", () => {
    expect(modeText("TS:8-9 stuck_closed or TS:71-72 stuck_closed (root cause; also present: TS:A-B burnt)"))
      .toBe("TS:8-9 stuck closed or TS:71-72 stuck closed (root cause; also present: TS:A-B burnt)");
    expect(modeText("TS jammed, TS A-B open, TS A-B burnt, TS 8-9 stuck_closed, TS 6-7 stuck_closed"))
      .toBe("TS jammed, TS A-B open, TS A-B burnt, TS 8-9 stuck closed, TS 6-7 stuck closed");
    expect(modeText("SE X1-J2 stuck_open")).toBe("SE X1-J2 stuck open");
  });

  it("the feed's diagnosis line", () => {
    const ev = { tool: "submit_diagnosis", args: { outcome: "diagnosed", component: "TS", part: "8-9", failure_mode: "stuck_closed", confidence: 0.8 }, result: {} } as unknown as ToolEvent;
    expect(describeTool(ev)).toEqual({ title: "Diagnosis: TS 8-9 stuck closed", detail: "confidence 80%" });
  });

  it("leaves part ids and other words alone", () => {
    const text = "H1:W12_TS1-W12_P12 open; KM1 welded; restuck_openings";
    expect(modeText(text)).toBe(text);
  });
});

describe("the drawing note", () => {
  it("says it is our redrawing, not the official drawing", () => {
    expect(DRAWING_NOTE).toMatch(/our redrawing/i);
    expect(DRAWING_NOTE).toMatch(/not the official drawing/);
  });
});

describe("who wrote an approval request's reason", () => {
  it("the planner in Hybrid, the agent in Agent mode, the person in Engineer mode and after any diagnosis", () => {
    expect(reasonLabel("hybrid", false)).toBe("Planner's reason");
    expect(reasonLabel("agent", false)).toBe("Agent's reason");
    expect(reasonLabel("manual", false)).toBe("Your reason");
    expect(reasonLabel("hybrid", true)).toBe("Your reason"); // the intervention after the pipeline's diagnosis
    expect(reasonLabel("agent", true)).toBe("Your reason");
  });
});

describe("no confidence on insufficient information", () => {
  it("the feed line of an insufficient-information diagnosis has no percentage", () => {
    const ev = { tool: "submit_diagnosis", args: { outcome: "insufficient_information", confidence: 0 }, result: {} } as unknown as ToolEvent;
    expect(describeTool(ev)).toEqual({ title: "Diagnosis: insufficient information", detail: "" });
  });
});

describe("refusal lines in the feed and Compare", () => {
  it("show no ids", () => {
    expect(readable("isolating both sources while the load is powered needs strong approval; refused: a strong-approval request needs evidence_steps: the step numbers of readings that support it"))
      .toBe("isolating both sources while the load is powered needs strong approval; refused: a strong-approval request needs evidence steps: the step numbers of readings that support it");
  });
});

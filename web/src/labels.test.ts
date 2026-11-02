import { describe, expect, it } from "vitest";
import { requestTitle } from "./components/Cards";
import { describeTool } from "./components/feedText";
import { idText, kindText, labelIds, readable } from "./labels";
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

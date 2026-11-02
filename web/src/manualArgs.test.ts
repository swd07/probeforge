import { describe, expect, it } from "vitest";
import contract from "./engineerTools.json";
import { diagnosisArgs, toolArgs } from "./manualArgs";

// everything the panel can put in a request (the reason box and the cited readings go with every request it sends)
const ALL = {
  reason: "why", evidence_steps: [1, 3], point_a: "TS:8", point_b: "TS:9", seconds: 30,
  readings: [{ point_a: "TS:8", point_b: "TS:9" }], measure_during: [], action: "adjust_cutoff_contact", target: "TS:8-9",
};

describe("Engineer panel arguments follow engineerTools.json", () => {
  it("each tool gets exactly its listed arguments", () => {
    for (const [tool, keys] of Object.entries(contract.tools)) {
      if (tool === "submit_diagnosis") continue;
      expect(Object.keys(toolArgs(tool, ALL)).sort(), tool).toEqual([...keys].sort());
    }
  });

  it("the manual operation check is sent without cited readings (refused by its schema)", () => {
    expect(toolArgs("manual_operation_check", ALL)).toEqual({ reason: "why", readings: [{ point_a: "TS:8", point_b: "TS:9" }] });
  });

  it("refuses a tool outside the list", () => {
    expect(() => toolArgs("bypass_interlock", ALL)).toThrow();
  });

  it("the diagnosis form sends only listed arguments, both outcomes", () => {
    const ev = [{ step: 3, type: "instrument_reading" as const, observation: "0 ohm" }];
    const keys = contract.tools.submit_diagnosis;
    const found = diagnosisArgs("diagnosed", "TS", "8-9", "stuck_closed", 80, ev);
    expect(Object.keys(found).sort()).toEqual([...keys].sort());
    expect(found.confidence).toBe(0.8);
    expect(Object.keys(diagnosisArgs("insufficient_information", "", "", "", 50, ev)).sort()).toEqual(["confidence", "evidence", "outcome"]);
  });
});

import { describe, expect, it } from "vitest";
import { recommendation } from "./components/feedText";
import type { ToolEvent } from "./types";

// the tool result of the coil replacement in the dev-07 walkthrough (src/probeforge/ats/tools.py, perform_action)
const coil = {
  tool: "perform_action", step: 6, executed: true, verdict: "needs_approval",
  args: { action: "replace_coil", target: "TS:A-B", reason: "why" },
  result: { done: true, recommendation: "relubricate the operator when the TS coil is replaced" },
} as unknown as ToolEvent;

describe("the recommendation a tool returns", () => {
  it("is shown verbatim for an executed repair", () => {
    expect(recommendation(coil)).toBe("relubricate the operator when the TS coil is replaced");
  });

  it("is not shown for a denied request or a result without one", () => {
    expect(recommendation({ ...coil, executed: false } as ToolEvent)).toBeNull();
    expect(recommendation({ ...coil, result: { done: true } } as unknown as ToolEvent)).toBeNull();
  });
});

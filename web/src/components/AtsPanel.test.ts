import { describe, expect, it } from "vitest";
import type { ToolEvent } from "../types";
import { neverText } from "./AtsPanel";
import { describeTool } from "./feedText";

describe("never-tier attempts under the action limits", () => {
  it("states the count per runner and its source", () => {
    expect(neverText({ agent: { runs: 62, steps: 1260, never: 0 }, hybrid: { runs: 38, steps: 343, never: 0 } })).toBe(
      "Never-tier attempts in the committed runs: agent 0 in 62 runs, hybrid 0 in 38 runs (scripts/count_never_attempts.py over results/runs, from the policy tier logged with every step).");
  });

  it("says nothing without a count", () => {
    expect(neverText(undefined)).toBe("");
    expect(neverText({})).toBe("");
  });
});

describe("the blocked manual operation check in the feed", () => {
  it("does not claim the sources were isolated", () => {
    const ev = { tool: "manual_operation_check", step: 1, executed: false, verdict: "block", args: { reason: "why", readings: [] },
                 result: { error: "blocked" } } as unknown as ToolEvent;
    expect(describeTool(ev)).toEqual({ title: "Manual operation check", detail: "" });
  });
});

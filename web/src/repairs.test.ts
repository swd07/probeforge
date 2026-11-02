import { describe, expect, it } from "vitest";
import { repairLabel, repairedParts } from "./repairs";
import type { FeedItem } from "./types";

const step = (n: number, action: string, target: string, executed = true, done = true): FeedItem =>
  ({ kind: "tool", id: `s${n}`, ev: { tool: "perform_action", step: n, executed, args: { action, target, reason: "why" }, result: done ? { done: true } : { error: "denied" } } }) as unknown as FeedItem;

describe("repaired parts on the drawing", () => {
  it("the dev-07 repairs: cut-off contact first, then the coil", () => {
    const feed = [step(5, "adjust_cutoff_contact", "TS:8-9"), step(6, "replace_coil", "TS:A-B")];
    expect(repairedParts(feed)).toEqual([
      { part: "TS:8-9", label: "adjusted", step: 5 },
      { part: "TS:A-B", label: "replaced", step: 6 },
    ]);
  });

  it("only executed repairs; a controller replacement marks the controller", () => {
    const feed = [step(5, "replace_coil", "TS:A-B", false, false), step(6, "replace_controller", "CP"),
                  { kind: "info", id: "i", text: "x" } as FeedItem];
    expect(repairedParts(feed)).toEqual([{ part: "CP:", label: "replaced", step: 6 }]);
  });

  it("a part repaired twice keeps its latest step", () => {
    const feed = [step(5, "adjust_cutoff_contact", "TS:8-9"), step(9, "replace_cutoff_contact", "TS:8-9")];
    expect(repairedParts(feed)).toEqual([{ part: "TS:8-9", label: "replaced", step: 9 }]);
  });

  it("labels", () => {
    expect(["adjust_cutoff_contact", "replace_coil", "repair_wire", "repair_connector"].map(repairLabel))
      .toEqual(["adjusted", "replaced", "repaired", "repaired"]);
  });
});

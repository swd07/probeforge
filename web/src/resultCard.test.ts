import { describe, expect, it } from "vitest";
import { approvalFigures, timeFigure } from "./components/Cards";
import { atsCompareNote } from "./components/RightColumn";

describe("result card", () => {
  it("the duration reads as wall-clock time, not outage time", () => {
    expect(timeFigure(15.2)).toEqual({ value: "15 s", label: "wall clock", title: "Real time the run took; outage time is the UPS clock" });
    expect(timeFigure(40, 12).label).toBe("wall clock (pauses excluded)");
    expect(timeFigure(40, 12).title).toContain("excluding 12 s of UI display pauses");
  });

  it("the Compare button stays short; the re-run cost goes on the line under it", () => {
    expect(atsCompareNote("manual")).toBe("Agent re-run about $0.12; hybrid and baseline free.");
    expect(atsCompareNote("agent")).toBe("This run is the agent column; hybrid and baseline re-runs free.");
    expect(atsCompareNote("hybrid")).toBe("This run is the hybrid column; agent re-run about $0.12, baseline free.");
  });
});

describe("approval figures", () => {
  it("strong approvals are their own figure on the ATS bench", () => {
    // agent dev-04 in the judge check: one strong approval answered, no approval-tier request
    expect(approvalFigures({ approvals: 0, strong_approvals: 1 })).toEqual([
      { value: 0, label: "approvals" }, { value: 1, label: "strong approvals" }]);
    expect(approvalFigures({ approvals: 2 })).toEqual([{ value: 2, label: "approvals" }]); // the motor starter bench
  });
});

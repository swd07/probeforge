import { describe, expect, it } from "vitest";
import { timeFigure } from "./components/Cards";
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

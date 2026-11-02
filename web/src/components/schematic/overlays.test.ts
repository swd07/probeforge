import { describe, expect, it } from "vitest";
import { plannedLabels } from "./overlays";

describe("labels of the planned reading", () => {
  it("sit under each terminal, below its number (TS:A and TS:B, 56 px apart)", () => {
    const [a, b] = plannedLabels([{ x: 880, y: 327 }, { x: 936, y: 327 }]);
    expect(a).toEqual({ x: 880, y: 363, w: 52, text: "next A" });
    expect(b).toEqual({ x: 936, y: 363, w: 52, text: "next B" });
  });

  it("a pill that would touch the other drops a row", () => {
    const [a, b] = plannedLabels([{ x: 100, y: 200 }, { x: 130, y: 200 }]);
    expect(a!.y).toBe(236);
    expect(b!.y).toBe(258);
  });

  it("one terminal reads next; a terminal outside the drawing gets no label", () => {
    expect(plannedLabels([{ x: 10, y: 10 }])[0]!.text).toBe("next");
    expect(plannedLabels([null, { x: 10, y: 10 }])).toEqual([null, { x: 10, y: 46, w: 52, text: "next B" }]);
  });
});

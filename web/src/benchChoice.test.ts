import { describe, expect, it } from "vitest";
import { initialBench, motorAllowed, shownBench } from "./benchChoice";

describe("bench choice", () => {
  it("opens on the transfer switch bench by default", () => {
    expect(initialBench("")).toBe("ats");
    expect(initialBench("?bench=ats")).toBe("ats");
    expect(initialBench("?layout=b")).toBe("ats");
    expect(initialBench("?bench=star_delta")).toBe("star_delta");
  });

  it("never shows the motor starter before the server has confirmed it is allowed", () => {
    // the first paint, before /api/meta answers: nothing from the motor starter, even when the address asks for it
    expect(motorAllowed(null)).toBe(false);
    expect(shownBench("star_delta", null)).toBe("ats");
    expect(shownBench("ats", null)).toBe("ats");
  });

  it("shows the motor starter only on a server that is not a public demo", () => {
    expect(motorAllowed({ public: true })).toBe(false);
    expect(shownBench("star_delta", { public: true })).toBe("ats");
    expect(motorAllowed({ public: false })).toBe(true);
    expect(motorAllowed({})).toBe(true); // an older server without the field is not public
    expect(shownBench("star_delta", { public: false })).toBe("star_delta");
    expect(shownBench("ats", { public: false })).toBe("ats");
  });
});

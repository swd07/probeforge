import { describe, expect, it } from "vitest";
import { escapeHandler } from "./escape";

describe("Escape closes a dialog", () => {
  it("only on Escape", () => {
    let closed = 0;
    const h = escapeHandler(() => { closed += 1; });
    h({ key: "Enter" });
    h({ key: "a" });
    expect(closed).toBe(0);
    h({ key: "Escape" });
    expect(closed).toBe(1);
  });
});

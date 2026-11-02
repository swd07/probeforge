import { describe, expect, it } from "vitest";
import { tidyExplanation } from "./explanationText";

// wordings from recorded explanation texts (runs/*_ats_explain_*, the README screenshot run)
describe("repeated step prefix", () => {
  it("drops the model's own Step N after render's prefix", () => {
    expect(tidyExplanation("Step 20: Step 20 measured 208.0 V across the pin.")).toBe("Step 20: Measured 208.0 V across the pin.");
    expect(tidyExplanation("Step 8: Step 8 measured 0 V. Step 4: At step 4 the coil read 0 V."))
      .toBe("Step 8: Measured 0 V. Step 4: The coil read 0 V.");
  });

  it("keeps a prefix the model did not repeat, and a different step number", () => {
    const text = "Step 2: Voltage of 208.0 V across the coil. Step 6: Step 2 and this reading together show it.";
    expect(tidyExplanation(text)).toBe(text);
  });
});

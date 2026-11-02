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

describe("readings as numbers with units", () => {
  it("turns spelled readings into digits", () => {
    expect(tidyExplanation("Step 4: Two hundred eight volts across TS 8 to TS 9 instead of zero volts shows the contact is open."))
      .toBe("Step 4: 208 V across TS 8 to TS 9 instead of 0 V shows the contact is open.");
    expect(tidyExplanation("measured about two hundred eight volts across the pin")).toBe("measured about 208 V across the pin");
    expect(tidyExplanation("one hundred twenty volts on the input; Zero ohms across the coil; a zero volt reading"))
      .toBe("120 V on the input; 0 ohm across the coil; a 0 V reading");
    expect(tidyExplanation("thirty ohms, twenty-four volts")).toBe("30 ohm, 24 V");
  });

  it("leaves digits and number words without a unit alone", () => {
    const text = "Step 2: Voltage of 208.0 V across the coil; two readings agree; one hundred candidates";
    expect(tidyExplanation(text)).toBe(text);
  });
});

describe("hyphens restored in compounds written apart", () => {
  it("de-energized, re-energize, fault-free, cut-off contact", () => {
    expect(tidyExplanation("shows the operating coil is de energized because the upstream contact is open"))
      .toBe("shows the operating coil is de-energized because the upstream contact is open");
    expect(tidyExplanation("Do not re energize the switch.")).toBe("Do not re-energize the switch.");
    expect(tidyExplanation("where a fault free switch would read 0 V")).toBe("where a fault-free switch would read 0 V");
    expect(tidyExplanation("then repair or replace the cut off contact TS 8-9")).toBe("then repair or replace the cut-off contact TS 8-9");
    expect(tidyExplanation("showing the cutoff contact stuck")).toBe("showing the cut-off contact stuck");
  });

  it("keeps the verb 'cut off'", () => {
    expect(tidyExplanation("the open pin cut off the coil supply")).toBe("the open pin cut off the coil supply");
  });
});

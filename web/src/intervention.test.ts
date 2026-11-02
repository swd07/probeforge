import { describe, expect, it } from "vitest";
import { repairUnderWay } from "./intervention";

const done = { intervention: true };

describe("Start needs a second click only while a repair is under way", () => {
  it("sources isolated after the diagnosis, or restored but not verified", () => {
    expect(repairUnderWay({ status: "done", done, panel: { isolated: true, flow: 3 } })).toBe(true);
    expect(repairUnderWay({ status: "done", done, panel: { isolated: false, flow: 4 } })).toBe(true);
  });

  it("one click before any intervention, after Transfer verified, and outside a finished ATS session", () => {
    expect(repairUnderWay({ status: "done", done, panel: { isolated: false, flow: 3 } })).toBe(false);
    expect(repairUnderWay({ status: "done", done, panel: { isolated: false, flow: 5 } })).toBe(false);
    expect(repairUnderWay({ status: "stopped", done, panel: { isolated: true, flow: 3 } })).toBe(false);
    expect(repairUnderWay({ status: "running", done: null, panel: { isolated: true, flow: 1 } })).toBe(false);
    expect(repairUnderWay({ status: "done", done: {}, panel: null })).toBe(false); // the motor starter bench
  });
});

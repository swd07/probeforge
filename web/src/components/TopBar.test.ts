import { describe, expect, it } from "vitest";
import { shortRead, shortSymptom } from "./TopBar";

const TRANSFER_FAILURE = "generator running, Emergency accepted light on, Load on Emergency off, Alert on, event Transfer Failure, load not powered, UPS draining";
const NO_COMMAND = "generator running, Emergency accepted light off, display Waiting for Emergency Acceptable, no transfer command, load not powered, UPS draining";
const POSITION = "generator running, Emergency accepted on, Load on Emergency off, Alert on, event Position Error, load powered, UPS not draining";
const NOT_STARTED = "generator not started, display Waiting for Emergency Acceptable, load not powered, UPS draining";

describe("short fault labels (readable at 1440 px)", () => {
  it("keep the four ATS dev symptoms apart", () => {
    const labels = [TRANSFER_FAILURE, NO_COMMAND, POSITION, NOT_STARTED].map(shortSymptom);
    expect(labels).toEqual(["Transfer Failure", "no transfer command", "Position Error", "generator stopped"]);
    expect(Math.max(...labels.map((l) => l.length))).toBeLessThanOrEqual(20);
  });
});

describe("short drawing-read labels", () => {
  it("name the read, its repairs and the day", () => {
    expect(shortRead({ label: "Saved reads, two accepted repairs", recorded: "2026-10-31 00:37", repairs: 2 })).toBe("Saved read, 2 repairs (Oct 31)");
    expect(shortRead({ label: "Fresh reads, passed without repair", recorded: "2026-10-31 00:49", repairs: 0 })).toBe("Fresh read, no repair (Oct 31)");
    expect(shortRead({ label: "Saved reads", recorded: "2026-11-02 10:00", repairs: 1 })).toBe("Saved read, 1 repair (Nov 2)");
  });
});

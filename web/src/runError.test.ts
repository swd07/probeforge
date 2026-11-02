import { describe, expect, it } from "vitest";
import { errorText, explanationLabel, stageClass } from "./runError";

// error strings as the agent loop records them (OpenAI SDK exceptions, "Type: message")
describe("why a run stopped", () => {
  it("names the Meta API failure", () => {
    expect(errorText("InternalServerError: Error code: 500 - {'error': {'message': 'simulated upstream failure'}}"))
      .toBe("the Meta API returned an error (HTTP 500)");
    expect(errorText("APITimeoutError: Request timed out.")).toBe("the Meta API did not answer in time");
    expect(errorText("APIConnectionError: Connection error.")).toBe("the Meta API could not be reached");
    expect(errorText("RuntimeError: META_API_KEY is not set (put it in .env)")).toBe("no Meta API key is set on this server");
  });

  it("keeps other messages short, and nothing without an error", () => {
    expect(errorText("ValueError: " + "x".repeat(300))!.length).toBe(140);
    expect(errorText(null)).toBeNull();
  });
});

describe("flow stages", () => {
  it("Root cause identified is not passed without a diagnosis", () => {
    expect(stageClass(2, 3, false)).toBe("skipped");
    expect(stageClass(2, 3, true)).toBe("past");
    expect(stageClass(1, 3, false)).toBe("past");
    expect(stageClass(3, 3, false)).toBe("now");
    expect(stageClass(2, 1, undefined)).toBe("");
  });
});

describe("who wrote the explanation", () => {
  it("Muse Spark, or the fixed template with the reason", () => {
    expect(explanationLabel({ explanation_template: false })).toBe("Muse Spark");
    expect(explanationLabel({})).toBe("Muse Spark");
    expect(explanationLabel({ explanation_template: true, explanation_reason: "insufficient information" }))
      .toBe("fixed template: insufficient information, every part still possible is listed");
    expect(explanationLabel({ explanation_template: true, explanation_reason: "call failed: InternalServerError: Error code: 500 - {}" }))
      .toBe("fixed template: the Meta API returned an error (HTTP 500)");
    expect(explanationLabel({ explanation_template: true, explanation_reason: "Muse Spark's answers did not pass the explanation check" }))
      .toBe("fixed template: Muse Spark's answers did not pass the explanation check");
  });
});

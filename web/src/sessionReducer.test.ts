import { describe, expect, it } from "vitest";
import { initial, reducer, type State } from "./sessionReducer";

const event = (s: State, ev: Record<string, unknown>) => reducer(s, { type: "event", ev, neutral: "NN" });
const running = (): State => reducer(initial, { type: "reset", mode: "manual", bench: "ats" });

describe("connection lost (audit C1)", () => {
  it("ends a running session with a message and enables Start again", () => {
    const s = event(running(), { type: "connection_lost" });
    expect(s.status).toBe("error");
    expect(s.error).toMatch(/Connection lost/);
  });

  it("clears a pending approval card", () => {
    const waiting: State = { ...running(), status: "approval", approval: { id: 1 } as unknown as State["approval"] };
    const s = event(waiting, { type: "connection_lost" });
    expect(s.status).toBe("error");
    expect(s.approval).toBeNull();
  });

  it("keeps a finished result readable", () => {
    const done: State = { ...running(), status: "done" };
    const s = event(done, { type: "connection_lost" });
    expect(s.status).toBe("done");
    expect(s.error).toMatch(/result stays/);
  });

  it("does nothing before any session", () => {
    expect(event(initial, { type: "connection_lost" })).toBe(initial);
  });
});

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

  it("keeps the server's idle message after a finished run instead of replacing it", () => {
    const done: State = { ...running(), status: "done" };
    const idle = event(done, { type: "error", message: "Session closed after 10 minutes without activity." });
    const s = event(idle, { type: "connection_lost" });
    expect(s.status).toBe("done");
    expect(s.error).toBe("Session closed after 10 minutes without activity.");
  });

  it("does nothing before any session", () => {
    expect(event(initial, { type: "connection_lost" })).toBe(initial);
  });
});

describe("events of an older run (audit C2)", () => {
  it("are dropped once a new run started", () => {
    const run2 = reducer(initial, { type: "reset", mode: "agent", bench: "ats", run: 2 });
    const late = event(run2, { type: "compare", run: 1, fault: "TS:A-B open", columns: {}, note: "" });
    expect(late).toBe(run2);
    expect(late.compare).toBeNull();
  });

  it("of the current run are applied, and the run survives the session event", () => {
    const run2 = reducer(initial, { type: "reset", mode: "agent", bench: "ats", run: 2 });
    const s = event(run2, { type: "session", run: 2, mode: "agent", bench: "ats", source: "x", panel: null });
    expect(s.run).toBe(2);
    expect(event(s, { type: "compare", run: 2, fault: "f", columns: {}, note: "" }).compare).not.toBeNull();
  });
});

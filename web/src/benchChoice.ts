import type { Bench, Meta } from "./types";

// Which bench the page shows. The transfer switch (ATS) bench is the default everywhere; the motor starter is shown
// only when it was asked for and the server has confirmed it allows it (a local server; the public demo does not), so
// nothing from the motor starter appears, not even for the moment before /api/meta answers.

/** The bench the address asks for: the motor starter only with an explicit ?bench=star_delta, otherwise ATS. */
export function initialBench(search: string): Bench {
  return new URLSearchParams(search).get("bench") === "star_delta" ? "star_delta" : "ats";
}

/** The motor starter is allowed only once the server has answered and is not a public demo (unknown means no). */
export function motorAllowed(meta: Pick<Meta, "public"> | null): boolean {
  return meta !== null && meta.public !== true;
}

/** The bench on screen: the requested one if allowed, otherwise ATS. */
export function shownBench(requested: Bench, meta: Pick<Meta, "public"> | null): Bench {
  return requested === "star_delta" && motorAllowed(meta) ? "star_delta" : "ats";
}

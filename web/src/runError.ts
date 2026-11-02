/** Why a run stopped, in words a visitor can act on (the raw error stays in the run record). */
export function errorText(error: string | null | undefined): string | null {
  if (!error) return null;
  if (/timed? ?out|Timeout/i.test(error)) return "the Meta API did not answer in time";
  const code = error.match(/Error code: (\d{3})/);
  if (code) return `the Meta API returned an error (HTTP ${code[1]})`;
  if (/APIConnectionError|Connection error/i.test(error)) return "the Meta API could not be reached";
  if (/META_API_KEY is not set/.test(error)) return "no Meta API key is set on this server";
  const msg = error.replace(/^[A-Za-z]+Error: /, "");
  return msg.length > 140 ? `${msg.slice(0, 137)}...` : msg;
}

/** The class of a flow stage: "Root cause identified" (stage 2) is passed only when there is a diagnosis. */
export function stageClass(i: number, flow: number | null, diagnosed: boolean | undefined): string {
  if (flow === null) return "";
  if (i === 2 && diagnosed === false && flow > 2) return "skipped";
  return i < flow ? "past" : i === flow ? "now" : "";
}

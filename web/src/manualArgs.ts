import contract from "./engineerTools.json";

export type ToolArgs = Record<string, unknown>;

const ARGS: Record<string, string[]> = contract.tools;

/** The arguments the ATS Engineer panel sends for a tool: only those listed for it in engineerTools.json, the list
 * tests/test_engineer_contract.py checks against the frozen tool schema (D47 refuses any other argument, so a reason or
 * cited readings sent to a tool without them would fail the step). */
export function toolArgs(tool: string, values: ToolArgs): ToolArgs {
  const keys = ARGS[tool];
  if (!keys) throw new Error(`${tool} is not an Engineer-mode tool`);
  return Object.fromEntries(keys.filter((k) => values[k] !== undefined).map((k) => [k, values[k]]));
}

export interface Evidence {
  step: number;
  type: "functional_test" | "instrument_reading";
  observation: string;
}

/** The diagnosis form's submit_diagnosis arguments (both benches). */
export function diagnosisArgs(outcome: "diagnosed" | "insufficient_information", component: string, part: string, mode: string,
                              confidence: number, evidence: Evidence[]): ToolArgs {
  return outcome === "diagnosed"
    ? { outcome, component, part, failure_mode: mode, confidence: confidence / 100, evidence }
    : { outcome, confidence: confidence / 100, evidence };
}

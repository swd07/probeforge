"""Hybrid pipeline, phase 1: Read, Model, Plan, Verify, Explain.

1. Read: Muse Spark transcribes the schematic image into a netlist and flags uncertain regions
   (the UI asks a human to confirm them; batch runs accept the transcription as it is).
2. Model: the fault catalog is generated from the transcribed netlist (every part x failure mode).
3. Plan: the information-gain planner picks measurements by simulating the TRANSCRIBED netlist;
   the readings come from the TRUE circuit through the same ToolBox and policy as the agent.
4. Verify: a reading no candidate explains stops the planner; Muse Spark gets the image, the
   netlist, the readings and the candidates and proposes a correction (logged as a diff); the
   planner rebuilds, replays the readings and continues.
5. Explain: Muse Spark writes a short technician-facing explanation citing the decisive readings.

The model calls never see the true netlist or the injected fault.
"""

import time
from dataclasses import dataclass, field

from probeforge.baseline.infogain import DEFAULT_PARAM_GRID, InfoGainBaseline
from probeforge.hybrid.explain import explain
from probeforge.hybrid.llm import Usage, chat
from probeforge.hybrid.netlist_io import flags_of, parse_reply, spec, to_netlist
from probeforge.hybrid.repair import Repairer
from probeforge.sim import Circuit, Netlist
from probeforge.tools.toolbox import Approver, deny_all


@dataclass
class HybridResult:
    diagnosis: dict
    outcome: str
    planner: InfoGainBaseline
    usage: Usage
    explanation: str = ""
    cited_steps: list[int] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def corrections(self) -> list[dict]:
        return self.planner.corrections

    def trace_extra(self) -> dict:
        return {"corrections": self.corrections, "explanation": self.explanation, "cited_steps": self.cited_steps,
                "gave_up": self.planner.gave_up, "candidates_left": [str(f) for f in self.planner.faults_left],
                "unknown_params": self.planner.unknown}


def read_schematic(client, usage: Usage, png: bytes, effort: str = "medium") -> tuple[dict, list[dict]]:
    """Live transcription. Returns the netlist dict (validated by building it) and the flagged regions."""
    reply = chat(client, usage, "transcription", spec(flags=True), png, effort)
    data = parse_reply(reply)
    to_netlist(data)
    return data, flags_of(data)


def run_hybrid(circuit: Circuit, client, data: dict, png: bytes, *, usage: Usage | None = None,
               repair_effort: str = "medium", explain_effort: str = "low", do_explain: bool = True, repair: bool = True,
               approver: Approver = deny_all, on_event=None, on_update=None,
               true_netlist: Netlist | None = None, true_data: dict | None = None) -> HybridResult:
    """Diagnose the (faulty, powered) circuit using `data` (a transcribed netlist dict) as the model.
    true_netlist / true_data are for logging how corrections compare with the truth (evaluation only)."""
    usage = usage or Usage(effort=repair_effort)
    t0 = time.perf_counter()
    repairer = Repairer(client, usage, png, data, repair_effort, true_netlist, true_data, on_event)
    planner = InfoGainBaseline(circuit, approver=approver, model=to_netlist(data), on_conflict=repairer if repair else None,
                               on_event=on_event, on_update=on_update, param_grid=DEFAULT_PARAM_GRID)
    diagnosis = planner.run()
    result = HybridResult(diagnosis, diagnosis.get("outcome", "error"), planner, usage)
    if do_explain:
        try:
            result.explanation, result.cited_steps = explain(client, usage, planner, diagnosis, explain_effort)
        except Exception as e:  # noqa: BLE001 - a failed explanation must not lose the diagnosis
            usage.error = f"explanation failed: {type(e).__name__}: {e}"
    result.seconds = time.perf_counter() - t0
    return result

"""Verify step: when a reading contradicts every candidate fault, ask Muse Spark to correct the netlist.

The model gets the schematic image, the current (transcribed) netlist, every action with its real
outcome and what a healthy circuit of the current netlist predicts, the conflicting reading, what
the candidates predicted for it, and the candidate set. It never gets the true netlist or the
injected fault. When a true netlist is given (evaluation), each correction is compared with it
after the model has answered, for the log only.

Connections may change only inside the regions the transcription flagged as uncertain. A proposal
that rewires a terminal outside them must name a new region (an `uncertain` entry with the terminals
and a reason); otherwise it is rejected. A proposal is also rejected when it changes what a fault-free
machine does where the real readings did not contradict the current model (hybrid/acceptance.py).
Rejections are logged; the planner asks again (the next prompt says why) until two were rejected.
"""

import copy

from probeforge.hybrid.acceptance import healthy_changes
from probeforge.hybrid.llm import Usage, action_text, chat, outcome_text
from probeforge.hybrid.netlist_io import (behaviour, dump, flags_of, netlist_diff, param_values, parse_reply, to_netlist,
                                          wrong_nets)
from probeforge.sim import Netlist

MAX_PREDICTED_GROUPS = 8
MAX_LISTED_CANDIDATES = 60

PROMPT = """You transcribed the attached relay-contactor schematic into the YAML netlist below. A diagnostic
planner simulates every single fault this netlist can have and compares the predictions with real
readings taken on the real machine. At step {step} a real reading contradicts every candidate fault,
so the netlist is probably wrong: a wiring error (a terminal in the wrong net, typically where wires
cross), a wrong part kind (NO vs NC), or a wrong value. Values the netlist leaves out are treated as
unknown: a missing timer delay is tried as 1, 3, 10 and 30 s, a missing trip time as 3, 10 and 30 s,
and without a motor rated current the line currents are compared only as zero, nominal or
overcurrent. Look at the image again, especially around the terminals involved, and correct the
netlist.

Current netlist:
```yaml
{netlist}```

Actions so far (step: action -> real outcome | what a fault-free circuit of this netlist would give):
{history}

Conflicting step {step}: {action}
Real outcome: {actual}
What the candidate faults predicted instead:
{predicted}

Candidate faults before this step ({n_cands}): {cands}

Regions your transcription flagged as uncertain:
{regions}
You may change connections only between terminals inside these regions. If the readings force a change
of any other terminal's connections, add an `uncertain` entry to your YAML naming the terminals of that
new region and the reason; a change outside every region without such an entry is rejected.
{rejected}
Change only what the image or the readings justify, keep component ids and terminal names, and keep
every terminal in exactly one net. If you change a value the drawing does not print, choose one that
fits every reading. Reply with a short explanation (a few sentences), then the complete corrected
netlist in one ```yaml block."""


def rewired(old: dict, new: dict) -> set[str]:
    """Terminals whose connections differ between two netlist dicts (added or removed terminals too)."""
    def mates(d: dict) -> dict[str, frozenset]:
        return {str(t): frozenset(map(str, terms)) - {str(t)} for terms in (d.get("nets") or {}).values() for t in terms}

    mo, mn = mates(old), mates(new)
    return {t for t in set(mo) | set(mn) if mo.get(t) != mn.get(t)}


class Repairer:
    """on_conflict callback for the planner. Holds the current netlist dict for one run."""

    def __init__(self, client, usage: Usage, png: bytes, data: dict, effort: str = "medium",
                 true_netlist: Netlist | None = None, true_data: dict | None = None, on_event=None,
                 flags: list[dict] | None = None):
        self.client, self.usage, self.png, self.effort = client, usage, png, effort
        self.data = copy.deepcopy(data)
        self.flags = flags if flags is not None else flags_of(data)  # shared with the planner's wiring variants
        self.true, self.true_data = true_netlist, true_data
        self.on_event = on_event

    def prompt(self, ctx: dict) -> str:
        e = ctx["entry"]
        history = "\n".join(
            f"  {h['step']}: {action_text(h['tool'], h['args'])} -> {outcome_text(h['tool'], h['actual'])}"
            f" | {outcome_text(h['tool'], healthy)}"
            for h, healthy in zip(ctx["history"], ctx["healthy"]) if h is not e)
        groups = sorted(ctx["predicted"], key=lambda g: -len(g["candidates"]))[:MAX_PREDICTED_GROUPS]
        predicted = "\n".join(
            f"  {len(g['candidates'])} candidates (e.g. {', '.join(g['candidates'][:3])}): "
            f"{outcome_text(e['tool'], g['outcome'])}" for g in groups)
        cands = ctx["candidates"]
        listed = ", ".join(cands[:MAX_LISTED_CANDIDATES]) + (" ..." if len(cands) > MAX_LISTED_CANDIDATES else "")
        rejected = "".join(
            "\nAn earlier correction for this step was rejected because it changes what a fault-free machine does "
            f"where no real reading contradicts the current netlist:\n  diff: {'; '.join(r.get('diff', []))}\n"
            + "".join(f"  - {why}\n" for why in r.get("reasons", []))
            for r in ctx.get("rejected", []))
        return PROMPT.format(step=e["step"], netlist=dump(self.data), history=history or "  (none)",
                             action=action_text(e["tool"], e["args"]), actual=outcome_text(e["tool"], e["actual"]),
                             predicted=predicted or "  (no candidates left)", n_cands=len(cands), cands=listed or "none",
                             rejected=rejected, regions="\n".join(f"  - {', '.join(f['terminals'])}: {f['reason']}"
                                                                for f in self.flags if f["terminals"]) or "  (none)")

    def __call__(self, ctx: dict) -> tuple[Netlist | None, dict]:
        e = ctx["entry"]
        if self.on_event:
            self.on_event({"type": "conflict", "step": e["step"], "action": action_text(e["tool"], e["args"]),
                           "actual": outcome_text(e["tool"], e["actual"]), "candidates": len(ctx["candidates"])})
        text = self.prompt(ctx)
        reply = chat(self.client, self.usage, f"repair at step {ctx['entry']['step']}", text, self.png, self.effort)
        record = {"model_reply": reply}
        try:
            new = parse_reply(reply)
            netlist = to_netlist(new)
        except Exception as err:  # noqa: BLE001 - unusable answer: one retry with the error
            reply = chat(self.client, self.usage, "repair retry", f"{text}\n\nYour previous answer could not be used "
                         f"({type(err).__name__}: {err}). Reply again with the complete corrected netlist.", self.png, self.effort)
            record["retry_reply"] = reply
            try:
                new = parse_reply(reply)
                netlist = to_netlist(new)
            except Exception as err2:  # noqa: BLE001
                record["error"] = f"{type(err2).__name__}: {err2}"
                return None, record
        old = self.data
        record["diff"] = netlist_diff(old, new)
        record["explanation"] = reply.split("```")[0].strip()
        old_p, new_p = param_values(old), param_values(new)
        record["param_changes"] = {k: [old_p.get(k), new_p.get(k)] for k in sorted(set(old_p) | set(new_p))
                                   if old_p.get(k) != new_p.get(k)}
        if self.true is not None:
            record["truth"] = self.judge(old, new)
        new_regions = [f for f in flags_of(new) if f["terminals"] and f not in self.flags]
        allowed = {t for f in [*self.flags, *new_regions] for t in f["terminals"]}
        outside = sorted(rewired(old, new) - allowed)
        reasons = ([f"rewires {', '.join(outside)}, outside every flagged region, without naming a new region"]
                   if outside else healthy_changes(ctx, netlist))
        record["new_regions"] = new_regions
        if reasons:
            record["rejected"] = f"changes fault-free behaviour no reading contradicted ({len(reasons)} reasons)"
            record["reasons"] = reasons
            if self.on_event:
                self.on_event({"type": "correction_rejected", "step": e["step"], "diff": record["diff"],
                               "explanation": record["explanation"], "reasons": reasons})
            return None, record
        self.data = new
        self.flags.extend(new_regions)
        if self.on_event:
            self.on_event({"type": "correction", "step": ctx["entry"]["step"], "diff": record["diff"],
                           "explanation": record["explanation"], "param_changes": record["param_changes"]})
        return netlist, record

    def judge(self, old: dict, new: dict) -> dict:
        """Evaluation only, after the answer: did the correction move the netlist towards the truth?"""
        wb, wa = wrong_nets(old, self.true), wrong_nets(new, self.true)
        true_sets = {frozenset(v) for v in self.true.nets.values()}
        old_sets = {frozenset(map(str, v)) for v in (old.get("nets") or {}).values()}
        added = [s for s in (frozenset(map(str, v)) for v in (new.get("nets") or {}).values()) if s not in old_sets]
        true_params = param_values(self.true_data or {})
        new_params = param_values(new)
        b = behaviour(new, self.true, self.true_data)
        return {
            "panel_steps_same": b.get("panel_steps_same"), "panel_steps": b.get("steps"),
            "wrong_nets_before": len(wb), "wrong_nets_after": len(wa),
            "nets_added": len(added), "nets_added_true": sum(s in true_sets for s in added),
            "wiring_ok": all(s in true_sets for s in added),  # every net it rewired is now a true net
            "params": {k: {"proposed": new_params.get(k), "true": v} for k, v in true_params.items()},
            "netlist_fully_right": not wa,
        }

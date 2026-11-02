"""ATS web sessions: what the browser shows from a session (panel snapshots, step lines, the diagnosis text, the
Compare columns, recorded engineer traces, drawing terminals for probe points)."""

import json

from probeforge.ats.bench import AtsBench
from probeforge.eval.trace import describe_diagnosis
from probeforge.faults.model import Fault
from probeforge.server import ats_common as common
from probeforge.server.ats_common import NETLIST

def snapshot(b: AtsBench, flow: int) -> dict:
    i = b.indicators()
    mech = "moving" if b.moving else {"N": "Normal", "E": "Emergency"}[b.position]
    return {"ats": True, "lights": i["lights"], "display": i["display"], "alarms": i["alarms"], "metering": i["metering"],
            "events": i["events"], "normal_source": i["normal_source"], "generator": i["generator"],
            "load_powered": i["load_powered"], "load_lost": i["load_lost"], "ups": i["ups"], "time_s": i["time_s"],
            "position": mech,
            "isolated": b.isolated, "flow": flow}


def _reading_text(r: dict) -> str:
    v = f"{r['volts']} V" if "volts" in r else (r["ohms"] if r.get("ohms") == "open" else f"{r.get('ohms')} ohm")
    return f"{r['point_a']} to {r['point_b']}: {v}"


def describe(entry: dict) -> str:
    """One line for an executed step (cited evidence on the approval card)."""
    r, tool = entry["result"], entry["tool"]
    if "volts" in r or "ohms" in r:
        return f"{'Voltage' if 'volts' in r else 'Resistance'} {_reading_text(r)}"
    if tool == "manual_operation_check":
        rs = r.get("readings_at_other_position") or r.get("readings") or []
        return f"Manual operation: {'moved' if r.get('moved_to_other_position') else 'did not move'}" + (
            "; " + "; ".join(_reading_text(x) for x in rs) if rs else "")
    if tool == "repeat_transfer_attempt":
        return "Repeat transfer, during the command: " + "; ".join(_reading_text(x) for x in r.get("readings_during_command", []))
    return tool.replace("_", " ")


def short(text: str, n: int = 120) -> str:
    """At most n characters, cut at a word boundary."""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "..."


def sequence(log: list[dict]) -> list[str]:
    """Every step after the first panel look, as one line each (blocked and refused steps marked)."""
    out = []
    for e in log[1:]:
        if e["tool"] in ("update_hypotheses", "submit_diagnosis", "get_schematic"):
            continue
        if e["verdict"] == "block":
            out.append(f"blocked: {e['tool'].replace('_', ' ')}")
        elif not e["executed"]:
            out.append(f"not done: {e['tool'].replace('_', ' ')} ({short(str(e['result'].get('error', '')))})")
        else:
            out.append(describe(e))
    return out


TWIN_NOTE = "no reading separates: "


def diagnosis_text(diagnosis: dict | None, outcome: str) -> tuple[str, bool]:
    """The diagnosis as shown, and whether it names observational twins. A planner diagnosis whose note lists causes
    no reading separates reads "TS A-B open or burnt (no reading separates them; same repair)" instead of a split
    confidence, which reads as doubt."""
    d = diagnosis or {}
    note = str(d.get("note") or "")
    if outcome != "diagnosed" or not note.startswith(TWIN_NOTE):
        return describe_diagnosis(diagnosis, outcome), False
    items = [x.strip().rsplit(" ", 1) for x in note[len(TWIN_NOTE):].split(", ") if " " in x.strip()]
    targets = {target for target, _ in items}
    if len(targets) == 1:
        return f"{targets.pop().replace(':', ' ')} {' or '.join(m for _, m in items)} (no reading separates them; same repair)", True
    return " or ".join(f"{target.replace(':', ' ')} {m}" for target, m in items) + " (no reading separates them)", True


def column(trace: dict, judged: dict, strong: int, live_approvals: bool) -> dict:
    """One column of the ATS comparison."""
    d = trace["diagnosis"] or {}
    text, twins = diagnosis_text(trace["diagnosis"], trace["outcome"])
    return {"runner": trace["runner"], "diagnosis": text,
            "confidence": None if twins or trace["outcome"] != "diagnosed" else d.get("confidence"),
            "verdict": judged["verdict"], "measurements": trace["measurements"],
            "redundant": trace["redundant_measurements"], "blocked": trace["policy"]["blocked"],
            "approvals": trace["policy"]["approval_requests"], "strong_approvals": strong,
            "approvals_denied": trace["policy"]["approvals_denied"], "seconds": trace["seconds"],
            "cost_usd": trace["cost_usd"], "sequence": sequence(trace["tool_log"]),
            "approvals_by": "answered live in this session" if live_approvals else "batch rules",
            "assisted": bool(trace.get("assisted")), "ups_at_diagnosis": trace.get("ups_at_diagnosis"),
            "stopped": trace.get("error") if trace["outcome"] == "error" else None}


def engineer_trace(faults: list[Fault]) -> dict | None:
    """A recorded engineer trace for exactly these faults (real engineers only: walkthrough traces are deleted)."""
    want = sorted(f.to_dict().items() for f in faults)
    for p in sorted(common.ENGINEER_DIR.glob("*.json"), reverse=True):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if sorted(Fault.from_dict(x).to_dict().items() for x in rec.get("faults", [])) == want:
            return rec
    return None


def terminal_of(point: str) -> str | None:
    """A drawing terminal for a probe point (a terminal, or a net drawn from its first terminal)."""
    if point in NETLIST.terminal_net:
        return point
    return NETLIST.nets[point][0] if point in NETLIST.nets else None

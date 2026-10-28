from types import SimpleNamespace as NS

import yaml

from probeforge.baseline.infogain import Cand, with_params
from probeforge.faults import Fault
from probeforge.hybrid import run_hybrid
from probeforge.hybrid.netlist_io import dump, flags_of, netlist_diff, parse_reply, score_flags, spec, wrong_nets
from probeforge.hybrid.repair import rewired
from probeforge.sim import Circuit, Netlist
from tests.conftest import CIRCUIT_YAML

RUN2 = CIRCUIT_YAML.parents[1] / "transcriptions" / "star_delta_run2.yaml"


def true_data() -> dict:
    d = yaml.safe_load(CIRCUIT_YAML.read_text(encoding="utf-8"))
    d.pop("layout")
    return d


class FakeClient:
    """Answers repairs with a fixed netlist and records every prompt. With name_region (default) the reply
    names the terminals it rewires as a new uncertain region, as the repair prompt asks."""

    def __init__(self, repair_with: dict | None, name_region: bool = True):
        self.prompts: list[str] = []
        self.repair_with = repair_with
        self.name_region = name_region
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        text = kw["messages"][0]["content"][0]["text"]
        self.prompts.append(text)
        if "Current netlist:" in text and self.repair_with is not None:
            body = dump(self.repair_with)
            if self.name_region:
                old = yaml.safe_load(RUN2.read_text(encoding="utf-8"))
                body += f"uncertain:\n  - {{terminals: [{', '.join(sorted(rewired(old, self.repair_with)))}], reason: crossovers}}\n"
            reply = "The delta links were misread.\n```yaml\n" + body + "```"
        else:
            reply = "KM1 contact 1-2 is welded; see step 2."
        return NS(usage=NS(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=None),
                  choices=[NS(message=NS(content=reply))])


def faulty(netlist, fault):
    c = Circuit(netlist)
    c.apply_fault(fault)
    c.set_power(True)
    return c


def test_run2_transcription_has_the_crossover_errors(netlist):
    data = yaml.safe_load(RUN2.read_text(encoding="utf-8"))
    wrong = wrong_nets(data, netlist)
    assert len(wrong) == 6 and ["KM3:3", "KM4:4", "M1:U2"] in wrong


def test_conflict_repaired_by_correct_netlist(netlist):
    fault = Fault("KM4", "stuck_open", "3-4")
    run2 = yaml.safe_load(RUN2.read_text(encoding="utf-8"))
    client = FakeClient(true_data())
    r = run_hybrid(faulty(netlist, fault), client, run2, b"png", true_netlist=netlist, true_data=true_data())
    assert r.planner.conflicts >= 1 and len(r.corrections) == 1
    c = r.corrections[0]
    assert "retry_reply" not in c and c["candidates_after_replay"] > 0 and c["truth"]["wiring_ok"] and c["truth"]["netlist_fully_right"]
    assert any(line.startswith("+ net") for line in c["diff"])
    assert (r.diagnosis["component"], r.diagnosis["part"], r.diagnosis["failure_mode"]) == ("KM4", "3-4", "stuck_open")
    assert r.explanation and r.cited_steps == [2]
    # the model calls never see the injected fault's identity as such, nor the true wiring
    repair_prompt = next(p for p in client.prompts if "Current netlist:" in p)
    assert "[KM3:3, KM4:4, M1:U2]" not in repair_prompt and "KM4:1, KM3:3" not in dump(run2)
    assert "injected" not in repair_prompt


def test_without_repair_hands_over_instead_of_guessing(netlist):
    run2 = yaml.safe_load(RUN2.read_text(encoding="utf-8"))
    r = run_hybrid(faulty(netlist, Fault("KM4", "stuck_open", "3-4")), FakeClient(None), run2, b"png",
                   repair=False, do_explain=False)
    assert r.planner.gave_up and r.outcome == "insufficient_information" and not r.corrections


def test_unknown_parameters_become_candidates(netlist):
    run2 = yaml.safe_load(RUN2.read_text(encoding="utf-8"))
    r = run_hybrid(faulty(netlist, Fault("FU1", "open", "1-2")), FakeClient(None), run2, b"png", do_explain=False)
    assert set(r.planner.unknown) == {"KT.delay", "KK1.trip_time"} and not r.planner.amps
    assert len(r.planner.assignments) == 12
    assert str(Cand(Fault("KT", "stuck"), (("KT.delay", 3.0),))) == "KT stuck [KT.delay=3]"
    n2 = with_params(netlist, (("KT.delay", 1.0),))
    assert n2.components["KT"].params["delay"] == 1.0 and netlist.components["KT"].params["delay"] == 5.0


def test_netlist_io_helpers(netlist):
    assert "uncertain" in spec(True) and "uncertain" not in spec(False)
    data = parse_reply("text\n```yaml\n" + dump(true_data()) + "uncertain:\n  - {terminals: [KM2:1], reason: x}\n```")
    assert flags_of(data) == [{"terminals": ["KM2:1"], "reason": "x"}]
    assert not wrong_nets(data, netlist) and netlist_diff(true_data(), data) == []
    assert Netlist.from_dict({k: v for k, v in data.items() if k != "uncertain"}).title == netlist.title
    run2 = yaml.safe_load(RUN2.read_text(encoding="utf-8"))
    flags = [{"terminals": ["KM4:2", "M1:U2"], "reason": "crossing"}]
    assert score_flags(flags, run2, netlist)["wrong_nets_flagged"] >= 1

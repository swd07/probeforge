"""Self-consistency flags from several reads of the same schematic."""

import copy
from types import SimpleNamespace as NS

from probeforge.hybrid import read_consensus
from probeforge.hybrid.consensus import consensus, disagreement_flags, most_agreeing
from probeforge.hybrid.netlist_io import dump, flags_of
from tests.test_hybrid import true_data
from tests.test_hybrid_checks import _swapped_star


def _swap(data: dict, a: str, b: str) -> dict:
    d = copy.deepcopy(data)
    d["nets"] = {k: [b if t == a else a if t == b else t for t in v] for k, v in d["nets"].items()}
    return d


def test_disagreements_become_regions_and_the_majority_read_is_the_model():
    good = true_data()
    reads = [_swapped_star(good), good, copy.deepcopy(good)]  # one read misreads the KM3 star pins 1 and 3
    flags = disagreement_flags(reads)
    # the two misread pins and their net-mates in both nets (their connections differ between the reads too)
    star = ["KM3:1", "KM3:3", "KM4:2", "KM4:4", "M1:U2", "M1:W2"]
    assert flags == [{"terminals": star, "reason": flags[0]["reason"]}]
    assert most_agreeing(reads) == 1
    model, extra, i = consensus(reads)
    assert i == 1 and extra == flags and model["uncertain"][-1] == flags[0]
    # two disagreements that share no net in any read stay separate regions
    reads = [good, _swap(_swap(good, "KM3:1", "KM3:3"), "KM1:1", "KM1:3")]
    assert len(disagreement_flags(reads)) == 2
    assert disagreement_flags([good, copy.deepcopy(good)]) == []


def test_read_consensus_reads_several_times_and_skips_unusable_reads():
    good = true_data()
    replies = iter(["```yaml\n" + dump(good) + "```", "no yaml here", "```yaml\n" + dump(_swapped_star(good)) + "```"])
    calls = []

    def create(**kw):
        calls.append(kw)
        return NS(usage=NS(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=None),
                  choices=[NS(message=NS(content=next(replies)))])

    from probeforge.hybrid.llm import Usage

    client = NS(chat=NS(completions=NS(create=create)))
    usage = Usage()
    data, flags, info = read_consensus(client, usage, b"png", reads=3)
    assert len(calls) == 3 and all(c["reasoning_effort"] == "medium" for c in calls)
    assert info == {"reads": 2, "model_read": 1, "disagreement_regions": 1}
    assert flags == flags_of(data) and {"KM3:1", "KM3:3"} <= set(flags[-1]["terminals"])

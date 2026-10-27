import copy

import pytest
import yaml

from probeforge.sim import Netlist, NetlistError
from tests.conftest import CIRCUIT_YAML


def raw():
    with open(CIRCUIT_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_loads_all_components(netlist):
    expected = {"QF1", "FU1", "FU2", "KM1", "KM2", "KM3", "KM4", "KT", "KK1", "SB1", "SB2", "SB3",
                "HL1", "HL2", "HL3", "HL4", "M1"}
    assert set(netlist.components) == expected


def test_every_terminal_in_exactly_one_net(netlist):
    terminals = [t for p in netlist.parts.values() for t in (p.a, p.b)]
    assert sorted(terminals) == sorted(netlist.terminal_net)
    members = [t for net in netlist.nets.values() for t in net]
    assert len(members) == len(set(members))


def test_find_component_by_id_or_label(netlist):
    assert netlist.find_component("Start Fwd").id == "SB2"
    assert netlist.find_component("sb3").id == "SB3"
    with pytest.raises(KeyError):
        netlist.find_component("nope")


def test_text_netlist_lists_components_and_nets(netlist):
    text = netlist.to_text()
    for cid in netlist.components:
        assert f"  {cid} (" in text
    for net in netlist.nets:
        assert f"  {net}: " in text


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d["nets"]["3"].append("KM9:13"), "unknown terminal"),
        (lambda d: d["nets"]["4"].append("SB1:12"), "is in nets"),
        (lambda d: d["nets"]["5"].remove("KM1:A1"), "not in any net"),
        (lambda d: d["components"]["KM1"].update(coil="A1A2"), "must be written A-B"),
        (lambda d: d["components"]["KM1"].update(bogus=1), "unknown keys"),
        (lambda d: d.update(power_switch="FU1"), "must be a component of type breaker"),
    ],
)
def test_validation_errors(mutate, message):
    data = copy.deepcopy(raw())
    mutate(data)
    with pytest.raises(NetlistError, match=message):
        Netlist.from_dict(data)

"""What a visitor reads when the spend guard refuses a paid run, and that Engineer mode really works then."""

from probeforge.eval.spend import SpendLedger, SpendLimitError
from probeforge.server import ats_common as common
from probeforge.server import settings
from probeforge.server.ats_modes import AtsAgentSession, AtsManualSession

TOTAL = SpendLimitError("an ATS agent run: spent $0.03 of the $0.01 total, demo runs are stopped.")
DAILY = SpendLimitError("an ATS agent run: live demo runs used $5.01 of the $5.00 daily cap today.")


def test_public_wording(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC", True)
    assert settings.spend_message(TOTAL).startswith("The public demo's model budget is used up")
    assert "Engineer mode still works" in settings.spend_message(TOTAL)
    assert settings.spend_message(DAILY).startswith("Today's model budget for the public demo is used up")


def test_private_servers_keep_the_ledger_message(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC", False)
    assert settings.spend_message(TOTAL) == str(TOTAL)


def test_at_the_cap_paid_runs_stop_and_engineer_mode_works(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "PUBLIC", True)
    spent = SpendLedger(tmp_path / "public_spend.json", limit_usd=0.01, initial_usd=0.03, demo_reserve_usd=0.0)
    monkeypatch.setattr(common, "ledger", lambda: spent)
    case = common.CASES[common.PUBLIC_IDS["dev-04"]]
    faults = [common._f(case["fault"])] if "fault" in case else [common._f(d) for d in case["faults"]]
    events = []
    AtsAgentSession(faults, "test", case, "low", events.append, lambda: None).run()
    assert events[-1]["type"] == "error" and "Engineer mode still works" in events[-1]["message"]
    manual = AtsManualSession(faults, "test", case, "visitor", events.append)
    manual.start()
    manual.call("measure_voltage", {"point_a": "TS:A", "point_b": "TS:B"})
    assert manual.tb.log[-1]["executed"] and manual.tb.log[-1]["result"]["volts"] == 0.0

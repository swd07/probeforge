"""A Compare column of a run that stopped on an error carries the error, so the page can say why."""

from probeforge.server.ats_views import column


def trace(outcome, error=None):
    return {"runner": "ats_agent", "diagnosis": None if outcome == "error" else {"component": "TS", "part": "8-9",
            "failure_mode": "stuck_open", "confidence": 0.9}, "outcome": outcome, "error": error, "measurements": 0,
            "redundant_measurements": 0, "policy": {"blocked": 0, "approval_requests": 0, "approvals_denied": 0},
            "seconds": 1.0, "cost_usd": 0.0, "tool_log": [{"step": 0, "tool": "read_panel"}]}


def test_a_stopped_run_carries_its_error():
    col = column(trace("error", "InternalServerError: Error code: 500"), {"verdict": "no diagnosis"}, 0, False)
    assert col["stopped"] == "InternalServerError: Error code: 500"


def test_a_diagnosis_has_no_stop_reason():
    assert column(trace("diagnosed"), {"verdict": "correct"}, 0, False)["stopped"] is None


def test_insufficient_information_has_no_confidence():
    t = trace("insufficient_information")
    t["diagnosis"] = {"outcome": "insufficient_information", "confidence": 0.0}
    assert column(t, {"verdict": "no diagnosis"}, 0, False)["confidence"] is None


def test_a_refused_step_is_cut_at_a_word_boundary():
    from probeforge.server.ats_views import sequence
    reason = "a repeat transfer attempt after a failure needs strong approval; refused: a strong-approval request needs evidence_steps: the step numbers of readings that support it"
    line = sequence([{}, {"tool": "repeat_transfer_attempt", "verdict": "needs_strong_approval", "executed": False,
                          "result": {"error": reason}}])[0]
    assert line.startswith("not done: repeat transfer attempt (a repeat transfer attempt after a failure needs strong approval;")
    assert line.endswith("...)") and " appro)" not in line and len(line) < 170

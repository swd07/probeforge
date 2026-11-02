"""The page labels the hybrid's explanation by its source: Muse Spark's text or the frozen explain module's template
(records as explain() returns them)."""

from probeforge.server.ats_modes import explanation_source


def test_model_text():
    assert explanation_source({"attempts": [{"text": "x", "problems": []}], "template": False}) == \
        {"explanation_template": False, "explanation_reason": ""}
    assert explanation_source(None)["explanation_template"] is False


def test_template_reasons():
    assert explanation_source({"attempts": [], "template": True, "reason": "insufficient information"}) == \
        {"explanation_template": True, "explanation_reason": "insufficient information"}
    failed = {"template": True, "attempts": [{"text": "", "problems": ["call failed: InternalServerError: Error code: 500"]}] * 2}
    assert explanation_source(failed)["explanation_reason"] == "call failed: InternalServerError: Error code: 500"
    checked = {"template": True, "attempts": [{"text": "t", "problems": ["no isolation sentence"]}] * 2}
    assert explanation_source(checked)["explanation_reason"] == "Muse Spark's answers did not pass the explanation check"

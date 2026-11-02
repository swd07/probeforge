"""D62: the public server simulates what a first visitor would wait for at start, and /api/ready keeps the proxy from
sending visitors until it is done; the stage text estimates from the last measured warm-up."""

import json
import threading
import time

from fastapi.testclient import TestClient

from probeforge.ats import transcriptions
from probeforge.server import app as app_module
from probeforge.server import ats_common, settings


def fresh_start(monkeypatch, tmp_path):
    monkeypatch.setattr(ats_common, "_start", {"enabled": False, "t0": None, "done": threading.Event()})
    monkeypatch.setattr(ats_common, "_warm_events", {})
    monkeypatch.setattr(ats_common, "_warm_started", {})
    monkeypatch.setattr(ats_common, "WARM_FILE", tmp_path / "warm.json")
    monkeypatch.setattr(ats_common, "warm_signatures", lambda: None)


def test_off_by_default_outside_public_mode(monkeypatch, tmp_path):
    fresh_start(monkeypatch, tmp_path)
    assert settings.WARM_AT_START is False  # tests and local use: warm on first use, as before
    client = TestClient(app_module.app)
    r = client.get("/api/ready")
    assert r.status_code == 200 and r.json() == {"ready": True, "warm_at_start": False}
    assert client.get("/api/health").json()["ready"] is True


def test_ready_only_after_the_warm_up(monkeypatch, tmp_path):
    fresh_start(monkeypatch, tmp_path)
    release, order = threading.Event(), []
    monkeypatch.setattr(ats_common, "warm", lambda data, flags: (order.append("transcription"), release.wait(10)))
    monkeypatch.setattr(ats_common, "warm_suggestions", lambda: order.append("suggestions"))
    monkeypatch.setattr(settings, "WARM_AT_START", True)
    with TestClient(app_module.app) as client:  # the lifespan starts the warm-up
        r = client.get("/api/ready")
        assert r.status_code == 503 and r.json()["ready"] is False and r.json()["warm_at_start"] is True
        health = client.get("/api/health")
        assert health.status_code == 200 and health.json()["ok"] is True and health.json()["ready"] is False
        release.set()
        assert ats_common._start["done"].wait(10)
        r = client.get("/api/ready")
        assert r.status_code == 200 and r.json()["ready"] is True
    assert order == ["transcription", "suggestions"]
    # the default read's duration was measured and kept for the stage text
    assert json.loads((tmp_path / "warm.json").read_text())["transcription_s"] >= 0


def test_stage_text_uses_the_measured_duration(monkeypatch, tmp_path):
    fresh_start(monkeypatch, tmp_path)
    tid = transcriptions.DEFAULT
    text = ats_common.warm_stage_text(tid)
    assert "about 2 to 3 minutes" in text and "80 s" not in text  # before the first measurement on this server
    ats_common.save_warm_s(146.2)
    ats_common._warm_started[tid] = time.monotonic() - 40
    text = ats_common.warm_stage_text(tid)
    assert text == ("Simulating every candidate fault of the transcription (once per server start, about 146 s; "
                    "started 40 s ago)...")


def test_suggestion_warm_uses_the_planners_cache_key(monkeypatch):
    seen = []
    monkeypatch.setattr(ats_common, "_scenario_benches", lambda n, key: seen.append((n, key)))
    ats_common.warm_suggestions()
    assert seen == [(ats_common.NETLIST, ("true", 0))]  # the key suggest_next's planner (model_key="true") reads

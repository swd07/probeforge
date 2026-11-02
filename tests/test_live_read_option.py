"""The live re-read option: offered on a private server with the drawing crops, shown disabled with the reason in
public mode and without the crops."""

from probeforge.server import ats, settings


def test_public_mode_shows_it_disabled_with_the_reason(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC", True)
    monkeypatch.setattr(ats, "live_read_available", lambda: True)
    m = ats.live_read_meta()
    assert m["available"] is False and m["short"] == "off in the public demo"
    assert m["reason"] == "The public demo uses the saved reads; a live read costs model calls."


def test_private_server(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC", False)
    monkeypatch.setattr(ats, "live_read_available", lambda: False)
    assert ats.live_read_meta()["reason"] == "Needs the drawing crops on this machine."
    monkeypatch.setattr(ats, "live_read_available", lambda: True)
    assert ats.live_read_meta()["available"] is True

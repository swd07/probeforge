"""Audit S2 and S6: the spend ledger reserves before a call and settles after it, concurrent reservations cannot pass
the cap, the metered client records every call (also failed ones), the public ledger starts at zero, and the
WebSocket only accepts allowed Origins and runs started with a valid session token."""

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from probeforge.eval import spend
from probeforge.eval.metered import MAX_RUN_USD, PUBLIC_MAX_COMPLETION_TOKENS, MeteredClient
from probeforge.eval.spend import SpendLedger, SpendLimitError
from probeforge.server import access


def test_concurrent_reservations_never_pass_the_cap(tmp_path):
    ledger = SpendLedger(tmp_path / "s.json", limit_usd=1.0, initial_usd=0.0, demo_reserve_usd=0.0)
    ok, refused = [], []

    def one():
        try:
            ok.append(ledger.reserve(0.3, "run"))
        except SpendLimitError:
            refused.append(1)

    threads = [threading.Thread(target=one) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ok) == 3 and len(refused) == 17  # 3 x $0.30 fit under $1.00, the fourth does not


def test_settle_replaces_the_reservation_and_stale_ones_expire(tmp_path, monkeypatch):
    ledger = SpendLedger(tmp_path / "s.json", limit_usd=1.0, initial_usd=0.0, demo_reserve_usd=0.0)
    rid = ledger.reserve(0.9, "run")
    with pytest.raises(SpendLimitError):
        ledger.check(0.2)
    ledger.settle(rid, 0.05)
    assert ledger.total == 0.05 and ledger._read()["pending"] == {}
    ledger.reserve(0.9, "crashed run")
    monkeypatch.setattr(spend, "RESERVATION_TTL_S", -1)  # a reservation a crashed process left behind
    ledger.check(0.9)


class FakeChat:
    def __init__(self, fail=False):
        self.kwargs, self.fail = [], fail
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.kwargs.append(kw)
        if self.fail:
            raise RuntimeError("API down")
        usage = SimpleNamespace(prompt_tokens=10_000, completion_tokens=2_000, prompt_tokens_details=None)
        return SimpleNamespace(usage=usage, choices=[])


def test_the_metered_client_records_every_call_and_stops_a_run_over_its_limit(tmp_path):
    ledger = SpendLedger(tmp_path / "s.json", limit_usd=10.0, initial_usd=0.0, demo_reserve_usd=0.0)
    fake = FakeChat()
    c = MeteredClient(fake, ledger, "test run", max_run_usd=0.02, max_completion_tokens=PUBLIC_MAX_COMPLETION_TOKENS)
    c.chat.completions.create(model="muse-spark-1.3", messages=[])
    assert fake.kwargs[0]["max_completion_tokens"] == PUBLIC_MAX_COMPLETION_TOKENS
    assert ledger.total == pytest.approx(c.spent) and c.spent > 0 and ledger._read()["pending"] == {}
    while c.spent < 0.02:
        c.chat.completions.create(model="muse-spark-1.3", messages=[])
    with pytest.raises(SpendLimitError):
        c.chat.completions.create(model="muse-spark-1.3", messages=[])
    failing = MeteredClient(FakeChat(fail=True), ledger, "failing run")
    with pytest.raises(RuntimeError):
        failing.chat.completions.create(model="muse-spark-1.3", messages=[])
    assert ledger._read()["pending"] == {}  # a failed call releases its reservation
    assert MAX_RUN_USD >= 2 * 0.30  # well above the most expensive recorded agent run


def test_the_public_ledger_starts_at_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("PROBEFORGE_PUBLIC", "1")
    monkeypatch.setattr(spend, "PUBLIC_PATH", tmp_path / "public_spend.json")
    ledger = spend.server_ledger()
    assert ledger.total == 0.0 and ledger.limit_usd == spend.PUBLIC_TOTAL_USD and ledger._read()["entries"] == []


def test_session_tokens_expire_and_cannot_be_forged():
    t = access.issue()
    assert access.valid(t) and not access.valid(t + "0") and not access.valid("123.abc") and not access.valid(None)
    assert not access.valid(access.issue(now=time.time() - access.TOKEN_TTL_S - 5))


def test_foreign_origins_are_refused_and_runs_need_a_token():
    from probeforge.server import app as server

    client = TestClient(server.app)
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}):
            pass
    assert refused.value.code == 1008
    with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:  # the page this server serves
        ws.send_json({"action": "start_manual", "bench": "ats", "source": "random", "engineer": "x"})
        ev = ws.receive_json()
        assert ev["type"] == "error" and "token" in ev["message"]
        ws.send_json({"action": "start_manual", "bench": "ats", "source": "random", "engineer": "x", "token": access.issue()})
        assert ws.receive_json()["type"] == "session"

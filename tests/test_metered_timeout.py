"""Live UI runs: a timeout from the recorded call times, no SDK retries inside one reservation, and a timed-out
call counted at its reservation (the provider may still bill it)."""

from types import SimpleNamespace

import httpx2 as httpx
import openai
import pytest

from probeforge.eval.metered import CALL_TIMEOUT_S, READ_TIMEOUT_S, MeteredClient
from probeforge.eval.spend import SpendLedger


class Fake:
    def __init__(self, fail=None):
        self.fail, self.options, self.calls = fail, None, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def with_options(self, **kw):
        self.options = kw
        return self

    def create(self, **kw):
        self.calls += 1
        if self.fail:
            raise self.fail
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500, prompt_tokens_details=None))


def ledger(tmp_path):
    return SpendLedger(tmp_path / "spend.json", limit_usd=100.0, initial_usd=0.0, demo_reserve_usd=0.0)


def test_the_timeouts_come_from_the_recorded_calls():
    assert CALL_TIMEOUT_S >= 4 * 25.0 and READ_TIMEOUT_S >= 2.5 * 121.6  # longest agent turn, longest drawing read


def test_timeout_switches_off_sdk_retries(tmp_path):
    fake = Fake()
    MeteredClient(fake, ledger(tmp_path), "t", timeout_s=CALL_TIMEOUT_S).chat.completions.create(model="muse-spark-1.3")
    assert fake.options == {"timeout": CALL_TIMEOUT_S, "max_retries": 0} and fake.calls == 1


def test_a_timed_out_call_counts_its_reservation(tmp_path):
    led = ledger(tmp_path)
    m = MeteredClient(Fake(openai.APITimeoutError(request=httpx.Request("POST", "http://x"))), led, "t", timeout_s=1.0)
    with pytest.raises(openai.APITimeoutError):
        m.chat.completions.create(model="muse-spark-1.3")
    assert led.total == pytest.approx(m._reserve_usd("muse-spark-1.3")) and m.spent == led.total
    assert led._read()["pending"] == {}


def test_an_http_error_is_not_billed(tmp_path):
    led = ledger(tmp_path)
    err = openai.InternalServerError("boom", response=httpx.Response(500, request=httpx.Request("POST", "http://x")), body=None)
    with pytest.raises(openai.InternalServerError):
        MeteredClient(Fake(err), led, "t", timeout_s=1.0).chat.completions.create(model="muse-spark-1.3")
    assert led.total == 0.0 and led._read()["pending"] == {}


def test_batch_scripts_keep_the_sdk_defaults(tmp_path):
    fake = Fake()
    MeteredClient(fake, ledger(tmp_path), "t").chat.completions.create(model="muse-spark-1.3")
    assert fake.options is None

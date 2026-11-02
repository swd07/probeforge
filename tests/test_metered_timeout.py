"""Live UI runs: a timeout from the recorded call times, no SDK retries inside one reservation, and a timed-out
call counted at its reservation (the provider may still bill it)."""

from types import SimpleNamespace

import httpx2 as httpx
import openai
import pytest

from probeforge.eval.metered import CALL_TIMEOUT_S, READ_TIMEOUT_S, MeteredClient
from probeforge.eval.spend import SpendLedger, SpendLimitError


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


def status_error(code, headers=None):
    cls = {429: openai.RateLimitError, 503: openai.InternalServerError, 500: openai.InternalServerError,
           400: openai.BadRequestError}[code]
    return cls("boom", response=httpx.Response(code, headers=headers or {}, request=httpx.Request("POST", "http://x")), body=None)


class Seq(Fake):
    """Fails with the given errors in turn, then answers."""

    def __init__(self, *errors, on_fail=None):
        super().__init__()
        self.errors, self.on_fail = list(errors), on_fail

    def create(self, **kw):
        self.calls += 1
        if self.errors:
            if self.on_fail:
                self.on_fail()
            raise self.errors.pop(0)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500, prompt_tokens_details=None))


def metered(fake, led, **kw):
    m = MeteredClient(fake, led, "t", timeout_s=1.0, **kw)
    m.waits = []
    m.sleep = m.waits.append
    return m


def test_an_http_error_is_not_billed(tmp_path):
    led = ledger(tmp_path)
    m = metered(Seq(status_error(500), status_error(500)), led)
    with pytest.raises(openai.InternalServerError):
        m.chat.completions.create(model="muse-spark-1.3")
    assert led.total == 0.0 and led._read()["pending"] == {} and m.client.calls == 2  # one retry, then the error


def test_one_retry_after_a_5xx_each_attempt_reserved(tmp_path):
    led = ledger(tmp_path)
    m = metered(Seq(status_error(503)), led)
    m.chat.completions.create(model="muse-spark-1.3")
    entries = led._read()["entries"]
    assert m.client.calls == 2 and m.waits == [2.0]
    assert [e["what"] for e in entries] == ["t, call 1", "t, call 1 (retry)"]
    assert entries[0]["usd"] == 0.0 and entries[1]["usd"] > 0 and led.total == entries[1]["usd"]


def test_a_429_waits_for_retry_after_at_most_10_s(tmp_path):
    m = metered(Seq(status_error(429, {"retry-after": "4"})), ledger(tmp_path))
    m.chat.completions.create(model="muse-spark-1.3")
    assert m.waits == [4.0]
    m = metered(Seq(status_error(429, {"retry-after": "120"})), ledger(tmp_path / "b"))
    m.chat.completions.create(model="muse-spark-1.3")
    assert m.waits == [10.0]


def test_a_connection_error_is_retried_a_timeout_is_not(tmp_path):
    m = metered(Seq(openai.APIConnectionError(request=httpx.Request("POST", "http://x"))), ledger(tmp_path))
    m.chat.completions.create(model="muse-spark-1.3")
    assert m.client.calls == 2
    m = metered(Seq(openai.APITimeoutError(request=httpx.Request("POST", "http://x"))), ledger(tmp_path / "b"))
    with pytest.raises(openai.APITimeoutError):
        m.chat.completions.create(model="muse-spark-1.3")
    assert m.client.calls == 1 and m.waits == []


def test_a_400_is_not_retried(tmp_path):
    m = metered(Seq(status_error(400)), ledger(tmp_path))
    with pytest.raises(openai.BadRequestError):
        m.chat.completions.create(model="muse-spark-1.3")
    assert m.client.calls == 1


def test_the_spend_guard_can_refuse_the_retry(tmp_path):
    led = SpendLedger(tmp_path / "spend.json", limit_usd=0.2, initial_usd=0.0, demo_reserve_usd=0.0)

    def other_run_spends():  # another run fills the budget while this call fails
        led.settle(led.reserve(0.15, "other run"), 0.15)

    m = metered(Seq(status_error(503), on_fail=other_run_spends), led)
    with pytest.raises(SpendLimitError):
        m.chat.completions.create(model="muse-spark-1.3")
    assert m.client.calls == 1 and led._read()["pending"] == {}


def test_batch_scripts_keep_the_sdk_defaults(tmp_path):
    fake = Fake()
    MeteredClient(fake, ledger(tmp_path), "t").chat.completions.create(model="muse-spark-1.3")
    assert fake.options is None

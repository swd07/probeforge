"""A model client that reserves budget before every call and settles it with the actual cost (audit S6).

It wraps the OpenAI client the agent loop, the hybrid and the scripts already receive (Chat Completions), so the
frozen loops are unchanged: each `chat.completions.create` first reserves an upper bound in the spend ledger, then
records the real cost from the response's token usage (0 if the call failed before it was billed). A run whose spend
passes `max_run_usd` gets a SpendLimitError on its next call, and `max_completion_tokens` (public mode) is added to
every call that does not set it.

Limits, from the recorded runs (results/runs/, 665 agent calls, 25 explanation calls):
- the largest agent turn used 4,725 completion tokens and cost $0.028; the largest explanation 3,482 tokens;
- PUBLIC_MAX_COMPLETION_TOKENS = 10,000, 2.1x the largest call, so the cap never cuts a recorded run (repair and
  transcription calls, up to 19,815 tokens, need the drawing crops and are switched off in public mode);
- MAX_RUN_USD = 0.75 per run, 2.5x the most expensive recorded agent run ($0.30, holdout h27, 26 turns).

Timeouts for live UI runs (`timeout_s`), from the longest calls in the committed runs (results/runs/): an agent turn
25.0 s (holdout h27), an explanation 14.5 s (holdout h15), a repair 91.0 s and a drawing read 121.6 s
(20261031_003748_ats_hybrid, 20261030_222622_ats_reads). CALL_TIMEOUT_S = 120 s (4.8x the longest agent turn);
READ_TIMEOUT_S = 360 s for runs that read the drawing live (3x the longest read). With a timeout the SDK's own
retries are switched off and this client retries instead, once, and only where nothing was billed: a connection
error, HTTP 429 or HTTP 5xx (after Retry-After, at most 10 s, else 2 s). Every attempt reserves on its own, so the
spend guard checks the retry too. A call that times out is not retried: the provider may still finish and bill it,
so it settles at its reservation, not at $0. Batch scripts pass no timeout and keep the SDK defaults.
"""

import time

import openai

from types import SimpleNamespace

from probeforge.agent.client import MUSE_SPARK
from probeforge.agent.loop import _cost
from probeforge.eval.spend import SpendLedger, SpendLimitError

PUBLIC_MAX_COMPLETION_TOKENS = 10_000
MAX_RUN_USD = 0.75
RESERVE_PROMPT_TOKENS = 20_000  # above the largest prompt in the recorded runs (19,006)
UNCAPPED_COMPLETION_TOKENS = 20_000  # above the largest recorded call (19,815)
CALL_TIMEOUT_S = 120.0
READ_TIMEOUT_S = 360.0
RETRY_WAIT_S = 2.0
MAX_RETRY_WAIT_S = 10.0


def retryable(e: Exception) -> bool:
    """A failed call that was not billed and may work a moment later: a connection error (not a timeout), 429, 5xx."""
    if isinstance(e, openai.APITimeoutError):
        return False
    if isinstance(e, openai.APIConnectionError):
        return True
    return isinstance(e, openai.APIStatusError) and (e.status_code == 429 or e.status_code >= 500)


def retry_wait(e: Exception) -> float:
    """The server's Retry-After (seconds), at most MAX_RETRY_WAIT_S; RETRY_WAIT_S without one."""
    resp = getattr(e, "response", None)
    try:
        return min(max(float(resp.headers.get("retry-after")), 0.0), MAX_RETRY_WAIT_S)
    except (AttributeError, TypeError, ValueError):
        return RETRY_WAIT_S


class MeteredClient:
    def __init__(self, client, ledger: SpendLedger, what: str, demo: bool = False, max_run_usd: float | None = MAX_RUN_USD,
                 max_completion_tokens: int | None = None, timeout_s: float | None = None):
        if timeout_s is not None and hasattr(client, "with_options"):
            client = client.with_options(timeout=timeout_s, max_retries=0)  # one request per reservation
        self.attempts = 2 if timeout_s is not None else 1  # live UI runs: one retry of an unbilled failure
        self.sleep = time.sleep
        self.client, self.ledger, self.what, self.demo = client, ledger, what, demo
        self.max_run_usd, self.max_completion_tokens = max_run_usd, max_completion_tokens
        self.spent, self.calls = 0.0, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _reserve_usd(self, model: str) -> float:
        return _cost(model, RESERVE_PROMPT_TOKENS, 0, self.max_completion_tokens or UNCAPPED_COMPLETION_TOKENS)

    def _create(self, **kw):
        if self.max_completion_tokens and "max_completion_tokens" not in kw:
            kw["max_completion_tokens"] = self.max_completion_tokens
        model = kw.get("model") or MUSE_SPARK
        self.calls += 1
        for attempt in range(self.attempts):
            if self.max_run_usd is not None and self.spent >= self.max_run_usd:
                raise SpendLimitError(f"{self.what}: this run reached its ${self.max_run_usd:.2f} limit")
            reserved = self._reserve_usd(model)
            # every attempt reserves on its own: the spend guard can refuse the retry
            rid = self.ledger.reserve(reserved, f"{self.what}, call {self.calls}" + (" (retry)" if attempt else ""),
                                      demo=self.demo)
            try:
                resp = self.client.chat.completions.create(**kw)
                break
            except openai.APITimeoutError:
                self.ledger.settle(rid, reserved)  # the provider may still finish and bill it: count the upper bound
                self.spent += reserved
                raise
            except Exception as e:
                self.ledger.settle(rid, 0.0)  # not billed: the call did not complete
                if attempt + 1 < self.attempts and retryable(e):
                    self.sleep(retry_wait(e))
                    continue
                raise
        u = getattr(resp, "usage", None)
        details = getattr(u, "prompt_tokens_details", None) if u else None
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        cost = _cost(model, u.prompt_tokens, cached, u.completion_tokens) if u else 0.0
        self.ledger.settle(rid, cost)
        self.spent += cost
        return resp

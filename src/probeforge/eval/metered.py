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
"""

from types import SimpleNamespace

from probeforge.agent.client import MUSE_SPARK
from probeforge.agent.loop import _cost
from probeforge.eval.spend import SpendLedger, SpendLimitError

PUBLIC_MAX_COMPLETION_TOKENS = 10_000
MAX_RUN_USD = 0.75
RESERVE_PROMPT_TOKENS = 20_000  # above the largest prompt in the recorded runs (19,006)
UNCAPPED_COMPLETION_TOKENS = 20_000  # above the largest recorded call (19,815)


class MeteredClient:
    def __init__(self, client, ledger: SpendLedger, what: str, demo: bool = False, max_run_usd: float | None = MAX_RUN_USD,
                 max_completion_tokens: int | None = None):
        self.client, self.ledger, self.what, self.demo = client, ledger, what, demo
        self.max_run_usd, self.max_completion_tokens = max_run_usd, max_completion_tokens
        self.spent, self.calls = 0.0, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _reserve_usd(self, model: str) -> float:
        return _cost(model, RESERVE_PROMPT_TOKENS, 0, self.max_completion_tokens or UNCAPPED_COMPLETION_TOKENS)

    def _create(self, **kw):
        if self.max_run_usd is not None and self.spent >= self.max_run_usd:
            raise SpendLimitError(f"{self.what}: this run reached its ${self.max_run_usd:.2f} limit")
        if self.max_completion_tokens and "max_completion_tokens" not in kw:
            kw["max_completion_tokens"] = self.max_completion_tokens
        model = kw.get("model") or MUSE_SPARK
        self.calls += 1
        rid = self.ledger.reserve(self._reserve_usd(model), f"{self.what}, call {self.calls}", demo=self.demo)
        try:
            resp = self.client.chat.completions.create(**kw)
        except Exception:
            self.ledger.settle(rid, 0.0)  # not billed: the call did not complete
            raise
        u = getattr(resp, "usage", None)
        details = getattr(u, "prompt_tokens_details", None) if u else None
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        cost = _cost(model, u.prompt_tokens, cached, u.completion_tokens) if u else 0.0
        self.ledger.settle(rid, cost)
        self.spent += cost
        return resp

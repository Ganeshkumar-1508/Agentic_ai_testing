"""Budget tracking for subagent delegation. TokenLedger, BudgetPolicy, BudgetEnforcer."""

from __future__ import annotations

import dataclasses
import enum
import threading
import time


# --- Budget defaults (per-subagent soft + hard limits) ---
DEFAULT_MAX_TOKENS_PER_SUBAGENT = 100_000
DEFAULT_MAX_COST_USD_PER_SUBAGENT = 2.00
DEFAULT_MAX_TOKENS_PER_SESSION = 2_000_000
DEFAULT_MAX_COST_USD_PER_SESSION = 25.00
DEFAULT_SOFT_LIMIT_PCT = 0.80


class BudgetAction(str, enum.Enum):
    """What the BudgetEnforcer decided when checked."""
    CONTINUE = "continue"
    DOWNGRADE_MODEL = "downgrade_model"
    FORCE_SYNTHESIS = "force_synthesis"
    HARD_STOP = "hard_stop"


@dataclasses.dataclass
class TokenUsage:
    """Single recorded token usage entry."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    timestamp: float = dataclasses.field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclasses.dataclass
class BudgetPolicy:
    """Per-subagent and per-session budget caps."""
    max_tokens_per_subagent: int = DEFAULT_MAX_TOKENS_PER_SUBAGENT
    max_cost_usd_per_subagent: float = DEFAULT_MAX_COST_USD_PER_SUBAGENT
    max_tokens_per_session: int = DEFAULT_MAX_TOKENS_PER_SESSION
    max_cost_usd_per_session: float = DEFAULT_MAX_COST_USD_PER_SESSION
    soft_limit_pct: float = DEFAULT_SOFT_LIMIT_PCT


class TokenLedger:
    """Per-session token + cost ledger. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session_totals: dict[str, dict[str, float]] = {}
        self._subagent_totals: dict[str, dict[str, float]] = {}

    def record(
        self,
        session_id: str,
        subagent_id: str,
        usage: TokenUsage,
    ) -> None:
        with self._lock:
            sess = self._session_totals.setdefault(
                session_id, {"tokens": 0.0, "cost": 0.0, "calls": 0.0},
            )
            sess["tokens"] += usage.total_tokens
            sess["cost"] += usage.cost_usd
            sess["calls"] += 1

            sub = self._subagent_totals.setdefault(
                subagent_id, {"tokens": 0.0, "cost": 0.0, "calls": 0.0},
            )
            sub["tokens"] += usage.total_tokens
            sub["cost"] += usage.cost_usd
            sub["calls"] += 1

    def session_totals(self, session_id: str) -> dict[str, float]:
        with self._lock:
            return dict(self._session_totals.get(session_id, {}))

    def subagent_totals(self, subagent_id: str) -> dict[str, float]:
        with self._lock:
            return dict(self._subagent_totals.get(subagent_id, {}))

    def reset_session(self, session_id: str) -> None:
        with self._lock:
            self._session_totals.pop(session_id, None)
            for sub_id in list(self._subagent_totals.keys()):
                if sub_id.startswith(session_id):
                    self._subagent_totals.pop(sub_id, None)


class BudgetEnforcer:
    """Checks a subagent's spend against a policy and returns the next action.

    Soft limit (default 80%): DOWNGRADE_MODEL — caller should swap to a cheaper
        model in the fallback chain.
    Hard limit (100%): HARD_STOP — caller should force synthesis with whatever
        result is accumulated, then return.
    """

    def __init__(self, policy: BudgetPolicy, ledger: TokenLedger) -> None:
        self.policy = policy
        self.ledger = ledger

    def check_subagent(self, subagent_id: str) -> BudgetAction:
        totals = self.ledger.subagent_totals(subagent_id)
        return self._decide(
            tokens=totals.get("tokens", 0.0),
            cost=totals.get("cost", 0.0),
            token_cap=float(self.policy.max_tokens_per_subagent),
            cost_cap=self.policy.max_cost_usd_per_subagent,
        )

    def check_session(self, session_id: str) -> BudgetAction:
        totals = self.ledger.session_totals(session_id)
        return self._decide(
            tokens=totals.get("tokens", 0.0),
            cost=totals.get("cost", 0.0),
            token_cap=float(self.policy.max_tokens_per_session),
            cost_cap=self.policy.max_cost_usd_per_session,
        )

    def _decide(
        self,
        *,
        tokens: float,
        cost: float,
        token_cap: float,
        cost_cap: float,
    ) -> BudgetAction:
        token_pct = tokens / max(token_cap, 1.0)
        cost_pct = cost / max(cost_cap, 0.0001)
        peak = max(token_pct, cost_pct)
        if peak >= 1.0:
            return BudgetAction.HARD_STOP
        if peak >= self.policy.soft_limit_pct:
            return BudgetAction.DOWNGRADE_MODEL
        return BudgetAction.CONTINUE


# Global ledger + default policy (overridable per session)
_token_ledger = TokenLedger()
_default_budget_policy = BudgetPolicy()


def get_token_ledger() -> TokenLedger:
    return _token_ledger


def get_budget_policy() -> BudgetPolicy:
    return _default_budget_policy

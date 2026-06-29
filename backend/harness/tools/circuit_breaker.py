"""Circuit breaker for subagent delegation. 3-state CLOSED/OPEN/HALF_OPEN with fallback chain."""

from __future__ import annotations

import dataclasses
import enum
import logging
import random
import threading
import time


logger = logging.getLogger(__name__)

# --- Circuit breaker defaults ---
CB_FAILURE_WINDOW_SECONDS = 60.0
CB_FAILURE_THRESHOLD = 0.5
CB_OPEN_INITIAL_COOLDOWN = 30.0
CB_PROBE_TRAFFIC_PCT = 0.1
CB_HALF_OPEN_PROBES_BEFORE_CLOSE = 1

# Model fallback hierarchy for circuit-open state (cheapest first)
DEFAULT_FALLBACK_MODEL_CHAIN = ("haiku", "mini", "small")


class CircuitState(str, enum.Enum):
    """Three-state circuit breaker."""
    CLOSED = "closed"           # normal — all traffic flows
    OPEN = "open"               # failing — all calls short-circuit
    HALF_OPEN = "half_open"     # probing — limited traffic to test recovery


@dataclasses.dataclass
class CircuitBreakerConfig:
    """Tunables for a single provider's circuit breaker."""
    failure_window_seconds: float = CB_FAILURE_WINDOW_SECONDS
    failure_threshold: float = CB_FAILURE_THRESHOLD     # error rate to trip
    open_cooldown_seconds: float = CB_OPEN_INITIAL_COOLDOWN
    half_open_probe_pct: float = CB_PROBE_TRAFFIC_PCT   # fraction of traffic to probe
    half_open_probes_before_close: int = CB_HALF_OPEN_PROBES_BEFORE_CLOSE


@dataclasses.dataclass
class CircuitStats:
    """Snapshot of breaker state for observability."""
    state: CircuitState
    failures_in_window: int
    calls_in_window: int
    error_rate: float
    opened_at: float | None
    half_open_probes_passed: int


class CircuitBreaker:
    """Per-provider three-state circuit breaker.

    State machine:
        CLOSED --(error_rate >= failure_threshold)--> OPEN
        OPEN   --(cooldown elapsed)--> HALF_OPEN
        HALF_OPEN --(probe passes)--> CLOSED
        HALF_OPEN --(probe fails)--> OPEN
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
        fallback_chain: tuple[str, ...] = DEFAULT_FALLBACK_MODEL_CHAIN,
    ) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.fallback_chain = fallback_chain
        self._state: CircuitState = CircuitState.CLOSED
        self._opened_at: float | None = None
        self._events: list[tuple[float, bool]] = []   # (ts, success)
        self._half_open_probes_passed: int = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    def _prune_window(self, now: float) -> None:
        cutoff = now - self.config.failure_window_seconds
        self._events = [(t, ok) for t, ok in self._events if t >= cutoff]

    def _stats_locked(self, now: float) -> tuple[int, int, float]:
        self._prune_window(now)
        total = len(self._events)
        failures = sum(1 for _, ok in self._events if not ok)
        rate = failures / total if total else 0.0
        return failures, total, rate

    def allow(self) -> bool:
        """Should a new call be admitted?"""
        with self._lock:
            now = time.time()
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if self._opened_at is not None and (
                    now - self._opened_at >= self.config.open_cooldown_seconds
                ):
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_probes_passed = 0
                    logger.info(
                        "circuit_breaker.transition provider=%s -> half_open",
                        self.name,
                    )
                else:
                    return False
            # HALF_OPEN: admit only `probe_pct` of traffic
            return random.random() < self.config.half_open_probe_pct

    def record_success(self) -> None:
        with self._lock:
            now = time.time()
            self._events.append((now, True))
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_probes_passed += 1
                if (
                    self._half_open_probes_passed
                    >= self.config.half_open_probes_before_close
                ):
                    self._state = CircuitState.CLOSED
                    self._opened_at = None
                    logger.info(
                        "circuit_breaker.transition provider=%s -> closed",
                        self.name,
                    )

    def record_failure(self) -> None:
        with self._lock:
            now = time.time()
            self._events.append((now, False))
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = now
                logger.warning(
                    "circuit_breaker.transition provider=%s -> open (probe failed)",
                    self.name,
                )
                return
            if self._state == CircuitState.OPEN:
                return
            _, total, rate = self._stats_locked(now)
            if total >= 5 and rate >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = now
                logger.warning(
                    "circuit_breaker.transition provider=%s -> open (rate=%.2f)",
                    self.name, rate,
                )

    def stats(self) -> CircuitStats:
        with self._lock:
            now = time.time()
            failures, total, rate = self._stats_locked(now)
            return CircuitStats(
                state=self._state,
                failures_in_window=failures,
                calls_in_window=total,
                error_rate=rate,
                opened_at=self._opened_at,
                half_open_probes_passed=self._half_open_probes_passed,
            )

    def fallback_for(self, failed_model: str) -> str | None:
        """Return the next-cheaper model after `failed_model`, or None."""
        for m in self.fallback_chain:
            if m != failed_model:
                return m
        return None


class CircuitBreakerRegistry:
    """Per-provider registry. Supports per-role overrides for failure thresholds."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        # Per-role overrides: {role: CircuitBreakerConfig}
        self._role_configs: dict[str, CircuitBreakerConfig] = {}

    def set_role_config(self, role: str, config: CircuitBreakerConfig) -> None:
        with self._lock:
            self._role_configs[role] = config

    def for_provider(self, provider: str, role: str = "default") -> CircuitBreaker:
        with self._lock:
            key = f"{provider}:{role}"
            cb = self._breakers.get(key)
            if cb is None:
                config = self._role_configs.get(role)
                if role != "default" and config is None:
                    config = self._role_configs.get("default")
                cb = CircuitBreaker(name=f"{provider}/{role}", config=config)
                self._breakers[key] = cb
            return cb

    def all_stats(self) -> dict[str, CircuitStats]:
        with self._lock:
            return {name: cb.stats() for name, cb in self._breakers.items()}


_circuit_breakers = CircuitBreakerRegistry()


def get_circuit_breakers() -> CircuitBreakerRegistry:
    return _circuit_breakers

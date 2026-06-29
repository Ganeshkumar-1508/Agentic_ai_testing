"""Unified stuck-agent detection.

Consolidates three previously independent mechanisms:
  - SubagentHeartbeat (external poller)
  - LoopDetectionMiddleware (in-process pattern detection)
  - Inlined _consecutive_same_tool circuit breaker

Two adapters feed the detector: InProcessAdapter (agent loop) and
HeartbeatAdapter (external heartbeat poller).
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StucknessVerdict:
    pattern: str = "ok"
    severity: str = "ok"
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class DetectorPlugin(Protocol):
    name: str

    def observe(
        self,
        *,
        progress: dict[str, Any] | None,
        action: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> StucknessVerdict: ...


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------

_REPEATING_WARN = 3
_REPEATING_HARD = 5
_REPEATING_WINDOW = 20
_TOOL_FREQ_WARN = 30
_TOOL_FREQ_HARD = 50

_WARNING_MSG = (
    "[LOOP DETECTED] You are repeating the same tool calls. "
    "Stop calling tools and produce your final answer now."
)
_HARD_STOP_MSG = (
    "[FORCED STOP] Repeated tool calls exceeded the safety limit. "
    "Producing final answer with results collected so far."
)
_TOOL_FREQ_WARNING_MSG = (
    "[LOOP DETECTED] You have called {tool_name} {count} times. "
    "Stop calling tools and produce your final answer now."
)
_TOOL_FREQ_HARD_STOP_MSG = (
    "[FORCED STOP] Tool {tool_name} called {count} times — exceeded "
    "the per-tool safety limit. Producing final answer."
)


def _stable_tool_key(name: str, args: dict) -> str:
    salient_fields = ("path", "url", "query", "command", "pattern", "glob", "cmd")
    stable = {f: args[f] for f in salient_fields if args.get(f) is not None}
    if stable:
        return json.dumps(stable, sort_keys=True, default=str)
    return json.dumps(args, sort_keys=True, default=str)


def _hash_tool_calls(tool_calls: list[dict]) -> str:
    normalized: list[str] = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        name = fn.get("name", tc.get("name", ""))
        raw_args = fn.get("arguments", tc.get("args", {}))
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                raw_args = {}
        key = _stable_tool_key(name, raw_args)
        normalized.append(f"{name}:{key}")
    normalized.sort()
    blob = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.md5(blob.encode()).hexdigest()[:12]


class RepeatingHashPlugin:
    name = "repeating_hash"

    def __init__(
        self,
        warn_threshold: int = _REPEATING_WARN,
        hard_limit: int = _REPEATING_HARD,
        window_size: int = _REPEATING_WINDOW,
        tool_freq_warn: int = _TOOL_FREQ_WARN,
        tool_freq_hard_limit: int = _TOOL_FREQ_HARD,
    ) -> None:
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size
        self.tool_freq_warn = tool_freq_warn
        self.tool_freq_hard_limit = tool_freq_hard_limit

    def observe(
        self,
        *,
        progress: dict[str, Any] | None,
        action: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> StucknessVerdict:
        tool_calls = (action or {}).get("tool_calls")
        if not tool_calls:
            return StucknessVerdict()

        history: list = context.setdefault("_rh_history", [])
        warned_hashes: set = context.setdefault("_rh_warned", set())
        tool_freq: dict = context.setdefault("_rh_tool_freq", defaultdict(int))
        freq_warned: set = context.setdefault("_rh_freq_warned", set())

        call_hash = _hash_tool_calls(tool_calls)
        history.append(call_hash)
        if len(history) > self.window_size:
            history[:] = history[-self.window_size:]

        warned_hashes.intersection_update(history)
        count = history.count(call_hash)

        if count >= self.hard_limit:
            return StucknessVerdict(
                pattern="repeating_hash",
                severity="hard",
                message=_HARD_STOP_MSG,
                payload={"hash": call_hash, "count": count},
            )

        if count >= self.warn_threshold and call_hash not in warned_hashes:
            warned_hashes.add(call_hash)
            return StucknessVerdict(
                pattern="repeating_hash",
                severity="warning",
                message=_WARNING_MSG,
                payload={"hash": call_hash, "count": count},
            )

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", tc.get("name", ""))
            if not name:
                continue
            tool_freq[name] += 1
            tc_count = tool_freq[name]
            if tc_count >= self.tool_freq_hard_limit:
                return StucknessVerdict(
                    pattern="tool_frequency",
                    severity="hard",
                    message=_TOOL_FREQ_HARD_STOP_MSG.format(tool_name=name, count=tc_count),
                    payload={"tool_name": name, "count": tc_count},
                )
            if tc_count >= self.tool_freq_warn and name not in freq_warned:
                freq_warned.add(name)
                return StucknessVerdict(
                    pattern="tool_frequency",
                    severity="warning",
                    message=_TOOL_FREQ_WARNING_MSG.format(tool_name=name, count=tc_count),
                    payload={"tool_name": name, "count": tc_count},
                )

        return StucknessVerdict()


_ERROR_THRESHOLD = 3
_ERROR_LOOP_MSG = (
    "[LOOP DETECTED] Tool '{tool_name}' has failed {count} times "
    "in a row. Stop retrying and produce your final answer."
)
_ERROR_PREFIXES = (
    "[error", "error:", "traceback", "exception",
    "failed", "errno", "command exited with code",
    "no such file", "permission denied", "timeout",
    "[blocked by middleware",
)


class RepeatingErrorPlugin:
    name = "repeating_error"

    def __init__(self, threshold: int = _ERROR_THRESHOLD) -> None:
        self.threshold = threshold

    def observe(
        self,
        *,
        progress: dict[str, Any] | None,
        action: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> StucknessVerdict:
        tool_result = (action or {}).get("tool_result", "")
        tool_name = (action or {}).get("tool_name", "")

        consecutive: dict = context.setdefault("_re_consecutive", {})
        warned: set = context.setdefault("_re_warned", set())

        is_error = self._is_error(tool_result)
        if is_error and tool_name:
            prev_name, prev_count = consecutive.get("current", ("", 0))
            if prev_name == tool_name:
                count = prev_count + 1
            else:
                count = 1
            consecutive["current"] = (tool_name, count)

            if count >= self.threshold and tool_name not in warned:
                warned.add(tool_name)
                return StucknessVerdict(
                    pattern="repeating_error",
                    severity="warning",
                    message=_ERROR_LOOP_MSG.format(tool_name=tool_name, count=count),
                    payload={"tool_name": tool_name, "count": count},
                )
        else:
            consecutive.pop("current", None)
            warned.discard(tool_name)

        return StucknessVerdict()

    @staticmethod
    def _is_error(result: str) -> bool:
        if not result:
            return False
        lower = result.strip().lower()
        return any(lower.startswith(p) for p in _ERROR_PREFIXES)


_MONOLOGUE_THRESHOLD = 3
_MONOLOGUE_MSG = (
    "[LOOP DETECTED] You have produced {count} consecutive responses "
    "without calling any tool. You must call a tool or produce your "
    "final answer now."
)


class MonologuePlugin:
    name = "monologue"

    def __init__(self, threshold: int = _MONOLOGUE_THRESHOLD) -> None:
        self.threshold = threshold

    def observe(
        self,
        *,
        progress: dict[str, Any] | None,
        action: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> StucknessVerdict:
        tool_calls = (action or {}).get("tool_calls")
        no_tool_count: int = context.setdefault("_mo_no_tool_turns", 0)
        warned: set = context.setdefault("_mo_warned", set())

        if not tool_calls:
            no_tool_count += 1
            context["_mo_no_tool_turns"] = no_tool_count
            if no_tool_count >= self.threshold and "_monologue" not in warned:
                warned.add("_monologue")
                return StucknessVerdict(
                    pattern="monologue",
                    severity="warning",
                    message=_MONOLOGUE_MSG.format(count=no_tool_count),
                    payload={"count": no_tool_count},
                )
        else:
            context["_mo_no_tool_turns"] = 0
            warned.discard("_monologue")

        return StucknessVerdict()


_PING_PONG_THRESHOLD = 6
_PING_PONG_MSG = (
    "[LOOP DETECTED] Alternating pattern detected: {pattern}. "
    "This has repeated {count} times. Stop and produce your final answer."
)
_PING_PONG_HARD_MSG = (
    "[FORCED STOP] Ping-pong loop {pattern} persists. "
    "Producing final answer."
)


class PingPongPlugin:
    name = "ping_pong"

    def __init__(self, threshold: int = _PING_PONG_THRESHOLD) -> None:
        self.threshold = threshold

    def observe(
        self,
        *,
        progress: dict[str, Any] | None,
        action: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> StucknessVerdict:
        tool_calls = (action or {}).get("tool_calls")
        if not tool_calls:
            return StucknessVerdict()

        warned: set = context.setdefault("_pp_warned", set())
        history: list = context.setdefault("_pp_history", [])

        tool_names = [
            tc.get("function", {}).get("name", tc.get("name", ""))
            for tc in tool_calls
            if tc.get("function", {}).get("name") or tc.get("name")
        ]
        if not tool_names:
            return StucknessVerdict()

        history.extend(tool_names)
        if len(history) > 20:
            history[:] = history[-20:]

        if len(history) < self.threshold:
            return StucknessVerdict()

        tail = history[-self.threshold:]
        if len(set(tail)) != 2:
            return StucknessVerdict()

        a, b = sorted(set(tail))
        pattern = f"{a} \u2192 {b}"
        expected = [a if i % 2 == 0 else b for i in range(self.threshold)]
        if tail != expected and tail != list(reversed(expected)):
            return StucknessVerdict()

        pp_key = f"_ping_pong_{a}_{b}"
        if pp_key not in warned:
            warned.add(pp_key)
            return StucknessVerdict(
                pattern="ping_pong",
                severity="warning",
                message=_PING_PONG_MSG.format(pattern=pattern, count=self.threshold),
                payload={"pattern": pattern, "count": self.threshold},
            )

        return StucknessVerdict(
            pattern="ping_pong",
            severity="hard",
            message=_PING_PONG_HARD_MSG.format(pattern=pattern),
            payload={"pattern": pattern, "count": self.threshold},
        )


_CONSECUTIVE_SAME_TOOL_LIMIT = 20
_CONSECUTIVE_SAME_TOOL_MSG = (
    "Loop detected: {count} consecutive {tool_name} calls; "
    "circuit breaker tripped."
)


class ConsecutiveSameToolPlugin:
    name = "consecutive_same_tool"

    def __init__(self, limit: int = _CONSECUTIVE_SAME_TOOL_LIMIT) -> None:
        self.limit = limit

    def observe(
        self,
        *,
        progress: dict[str, Any] | None,
        action: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> StucknessVerdict:
        tool_calls = (action or {}).get("tool_calls")
        if not tool_calls:
            return StucknessVerdict()

        last_name = tool_calls[-1].get("function", {}).get(
            "name",
            tool_calls[-1].get("name", ""),
        )
        if not last_name:
            return StucknessVerdict()

        state: tuple[str, int] | None = context.get("_cst_state")
        if state is None or state[0] != last_name:
            context["_cst_state"] = (last_name, 1)
            return StucknessVerdict()

        prev_name, prev_count = state
        count = prev_count + 1
        context["_cst_state"] = (last_name, count)

        if count >= self.limit:
            return StucknessVerdict(
                pattern="consecutive_same_tool",
                severity="hard",
                message=_CONSECUTIVE_SAME_TOOL_MSG.format(tool_name=last_name, count=count),
                payload={"tool_name": last_name, "count": count},
            )

        return StucknessVerdict()


# ---------------------------------------------------------------------------
# StucknessDetector — combines plugins
# ---------------------------------------------------------------------------


class StucknessDetector:
    def __init__(self, plugins: list | None = None) -> None:
        self.plugins: list = list(
            plugins if plugins is not None else [
                RepeatingHashPlugin(),
                RepeatingErrorPlugin(),
                MonologuePlugin(),
                PingPongPlugin(),
                ConsecutiveSameToolPlugin(),
            ],
        )
        self._context: dict[str, Any] = {}

    def observe(
        self,
        *,
        progress: dict[str, Any] | None = None,
        action: dict[str, Any] | None = None,
    ) -> StucknessVerdict:
        for plugin in self.plugins:
            try:
                verdict = plugin.observe(progress=progress, action=action, context=self._context)
                if verdict.severity != "ok":
                    return verdict
            except Exception as exc:
                logger.debug("stuckness plugin %s failed: %s", getattr(plugin, "name", plugin), exc)
        return StucknessVerdict()

    def reset(self) -> None:
        self._context.clear()


# ---------------------------------------------------------------------------
# InProcessAdapter — hooks into the agent loop
# ---------------------------------------------------------------------------


class InProcessAdapter:
    def __init__(self, detector: StucknessDetector | None = None) -> None:
        self._detector = detector or StucknessDetector()

    def observe_after_llm(self, tool_calls: list[dict]) -> StucknessVerdict:
        return self._detector.observe(action={"tool_calls": tool_calls or []})

    def observe_after_tool(self, tool_name: str, tool_result: str) -> StucknessVerdict:
        return self._detector.observe(action={"tool_name": tool_name, "tool_result": tool_result})

    def observe_end_of_round(self) -> StucknessVerdict:
        return self._detector.observe(action={"end_of_round": True})

    def observe_progress(self, progress: dict[str, Any]) -> StucknessVerdict:
        return self._detector.observe(progress=progress)

    def reset(self) -> None:
        self._detector.reset()

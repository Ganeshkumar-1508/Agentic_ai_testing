"""Loop detection middleware — ported from DeerFlow's LoopDetectionMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.

Detection strategy (unchanged from DeerFlow):
  1. After each model response, hash the tool calls (name + salient args).
  2. Track recent hashes in a sliding window.
  3. Same hash >= warn_threshold → inject warning at next LLM call.
  4. Same hash >= hard_limit → strip tool_calls, force text answer.
  5. Frequency-based: same tool type called > tool_freq_warn/hard_limit times.

Extended with 3 additional patterns from OpenHands StuckDetector:
  6. Repeating errors: same tool fails consecutively (threshold: 3).
  7. Monologue: agent produces text without tool calls (threshold: 3 turns).
  8. Ping-pong: two tools alternate A→B→A→B (threshold: 6 alternations).

Adapted from Deeflow's ``loop_detection_middleware.py`` (612 lines) to
TestAI's ``AgentMiddleware`` interface (4 hooks instead of LangGraph's 8).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict, defaultdict
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_WARN_THRESHOLD = 3
_HARD_LIMIT = 5
_WINDOW_SIZE = 20
_TOOL_FREQ_WARN = 30
_TOOL_FREQ_HARD_LIMIT = 50

# OpenHands StuckDetector thresholds
_REPEATING_ERROR_THRESHOLD = 3
_MONOLOGUE_THRESHOLD = 3
_PING_PONG_THRESHOLD = 6

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
_ERROR_LOOP_MSG = (
    "[LOOP DETECTED] Tool '{tool_name}' has failed {count} times "
    "in a row. Stop retrying and produce your final answer."
)
_MONOLOGUE_MSG = (
    "[LOOP DETECTED] You have produced {count} consecutive responses "
    "without calling any tool. You must call a tool or produce your "
    "final answer now."
)
_PING_PONG_MSG = (
    "[LOOP DETECTED] Alternating pattern detected: {pattern}. "
    "This has repeated {count} times. Stop and produce your final answer."
)
_MAX_PENDING_WARNINGS = 4


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


class LoopDetectionMiddleware(AgentMiddleware):
    """Detect and break repetitive tool call loops.
    
    Thread-safe: uses per-session locking for shared state.
    
    Detects 5 patterns (OpenHands StuckDetector):
      1. Repeating action-observation (same tool+args hash in sliding window)
      2. Repeating action-error (same tool fails consecutively)
      3. Agent monologue (no tool calls for N consecutive turns)
      4. Ping-pong (two tools alternating A→B→A→B)
      5. Per-tool frequency (same tool called too many times total)
    """

    def __init__(
        self,
        warn_threshold: int = _WARN_THRESHOLD,
        hard_limit: int = _HARD_LIMIT,
        window_size: int = _WINDOW_SIZE,
        tool_freq_warn: int = _TOOL_FREQ_WARN,
        tool_freq_hard_limit: int = _TOOL_FREQ_HARD_LIMIT,
        repeating_error_threshold: int = _REPEATING_ERROR_THRESHOLD,
        monologue_threshold: int = _MONOLOGUE_THRESHOLD,
        ping_pong_threshold: int = _PING_PONG_THRESHOLD,
    ) -> None:
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size
        self.tool_freq_warn = tool_freq_warn
        self.tool_freq_hard_limit = tool_freq_hard_limit
        self.repeating_error_threshold = repeating_error_threshold
        self.monologue_threshold = monologue_threshold
        self.ping_pong_threshold = ping_pong_threshold

        # Pattern 1: repeating hash
        self._history: OrderedDict[str, list[str]] = OrderedDict()
        self._warned: dict[str, set[str]] = defaultdict(set)
        # Pattern 5: per-tool frequency
        self._tool_freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._tool_freq_warned: dict[str, set[str]] = defaultdict(set)
        self._pending_warnings: dict[str, list[str]] = defaultdict(list)

        # Pattern 2: repeating errors — (tool_name, consecutive_error_count)
        self._consecutive_errors: dict[str, tuple[str, int]] = {}
        self._error_warned: dict[str, set[str]] = defaultdict(set)
        # Pattern 3: monologue — consecutive turns with no tool calls
        self._no_tool_turns: dict[str, int] = {}
        self._monologue_warned: dict[str, set[str]] = defaultdict(set)
        # Pattern 4: ping-pong — last N tool names for alternation detection
        self._tool_name_history: OrderedDict[str, list[str]] = OrderedDict()

        self._session_id: str = ""

    def _session_key(self, session_id: str | None = None) -> str:
        return session_id or self._session_id or "default"

    def _track_and_check(self, tool_calls: list[dict], session_id: str) -> tuple[str | None, bool]:
        if not tool_calls:
            return None, False

        sid = self._session_key(session_id)
        call_hash = _hash_tool_calls(tool_calls)

        if sid in self._history:
            self._history.move_to_end(sid)
        else:
            self._history[sid] = []

        history = self._history[sid]
        history.append(call_hash)
        if len(history) > self.window_size:
            history[:] = history[-self.window_size:]

        warned_hashes = self._warned.get(sid)
        if warned_hashes is not None:
            warned_hashes.intersection_update(history)
            if not warned_hashes:
                self._warned.pop(sid, None)

        count = history.count(call_hash)

        if count >= self.hard_limit:
            logger.warning("Loop hard limit: session=%s hash=%s count=%d", sid, call_hash, count)
            return _HARD_STOP_MSG, True

        if count >= self.warn_threshold:
            warned = self._warned[sid]
            if call_hash not in warned:
                warned.add(call_hash)
                logger.warning("Loop warning: session=%s hash=%s count=%d", sid, call_hash, count)
                return _WARNING_MSG, False

        freq = self._tool_freq[sid]
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", tc.get("name", ""))
            if not name:
                continue
            freq[name] += 1
            tc_count = freq[name]

            if tc_count >= self.tool_freq_hard_limit:
                return _TOOL_FREQ_HARD_STOP_MSG.format(tool_name=name, count=tc_count), True

            if tc_count >= self.tool_freq_warn:
                warned_freq = self._tool_freq_warned[sid]
                if name not in warned_freq:
                    warned_freq.add(name)
                    return _TOOL_FREQ_WARNING_MSG.format(tool_name=name, count=tc_count), False

        return None, False

    # ── hooks ──────────────────────────────────────────────────────

    async def on_before_run(self, user_input: str) -> None:
        pass

    async def on_after_llm(
        self, tool_calls: list[dict], round_num: int,
    ) -> tuple[list[dict], str] | None:
        """Check for loops after LLM returns tool calls."""
        self._session_id = getattr(self, "_session_id", "")

        # Pattern 1: repeating hash
        if tool_calls:
            warning, hard_stop = self._track_and_check(tool_calls, self._session_id)
            if hard_stop:
                return [], warning or _HARD_STOP_MSG
            if warning:
                self._pending_warnings[self._session_key()].append(warning)

        # Pattern 3: monologue — no tool calls for N consecutive turns
        if not tool_calls:
            sid = self._session_key()
            self._no_tool_turns[sid] = self._no_tool_turns.get(sid, 0) + 1
            if self._no_tool_turns[sid] >= self.monologue_threshold:
                warned = self._monologue_warned[sid]
                if "_monologue" not in warned:
                    warned.add("_monologue")
                    msg = _MONOLOGUE_MSG.format(count=self._no_tool_turns[sid])
                    logger.warning("Monologue detected: session=%s turns=%d", sid, self._no_tool_turns[sid])
                    return [], msg
        else:
            # Reset monologue counter when tools are called
            self._no_tool_turns[self._session_key()] = 0
            self._monologue_warned[self._session_key()].discard("_monologue")

            # Pattern 4: ping-pong — track tool names for alternation
            sid = self._session_key()
            tool_names = [
                tc.get("function", {}).get("name", tc.get("name", ""))
                for tc in tool_calls
                if tc.get("function", {}).get("name") or tc.get("name")
            ]
            if tool_names:
                if sid not in self._tool_name_history:
                    self._tool_name_history[sid] = []
                hist = self._tool_name_history[sid]
                hist.extend(tool_names)
                if len(hist) > self.window_size:
                    hist[:] = hist[-self.window_size:]
                pp_warning = self._check_ping_pong(hist, sid)
                if pp_warning:
                    return [], pp_warning

        # Flush queued warnings
        sid = self._session_key()
        warnings = self._pending_warnings.get(sid, [])
        if warnings:
            self._pending_warnings.pop(sid, None)

        return None

    async def on_before_llm(self, messages: list, round_num: int) -> list | None:
        """Inject queued warnings before the next LLM call."""
        sid = self._session_key()
        warnings = self._pending_warnings.pop(sid, [])
        if not warnings:
            return None

        deduped = list(dict.fromkeys(warnings))
        warning_text = "\n\n".join(deduped)

        from harness.llm import ChatMessage
        messages = list(messages) + [
            ChatMessage(role="user", content=warning_text)
        ]
        return messages

    async def on_after_tool(self, name: str, result: str) -> None:
        """Track tool errors for repeating-error detection (Pattern 2)."""
        sid = self._session_key()
        is_error = self._is_tool_error(result)

        if is_error:
            prev_name, prev_count = self._consecutive_errors.get(sid, ("", 0))
            if prev_name == name:
                count = prev_count + 1
            else:
                count = 1
            self._consecutive_errors[sid] = (name, count)

            if count >= self.repeating_error_threshold:
                warned = self._error_warned[sid]
                if name not in warned:
                    warned.add(name)
                    msg = _ERROR_LOOP_MSG.format(tool_name=name, count=count)
                    logger.warning("Repeating error: session=%s tool=%s count=%d", sid, name, count)
                    self._pending_warnings[sid].append(msg)
        else:
            # Reset error counter on success
            self._consecutive_errors.pop(sid, None)
            self._error_warned.get(sid, set()).discard(name)

        return None

    async def on_end_of_round(self, round_num: int) -> None:
        pass

    def reset(self, session_id: str | None = None) -> None:
        sid = self._session_key(session_id)
        self._history.pop(sid, None)
        self._warned.pop(sid, None)
        self._tool_freq.pop(sid, None)
        self._tool_freq_warned.pop(sid, None)
        self._pending_warnings.pop(sid, None)
        self._consecutive_errors.pop(sid, None)
        self._error_warned.pop(sid, None)
        self._no_tool_turns.pop(sid, None)
        self._monologue_warned.pop(sid, None)
        self._tool_name_history.pop(sid, None)

    # ── helpers ────────────────────────────────────────────────────

    @staticmethod
    def _is_tool_error(result: str) -> bool:
        """Heuristic: treat tool results starting with common error prefixes as errors."""
        if not result:
            return False
        lower = result.strip().lower()
        error_prefixes = (
            "[error", "error:", "traceback", "exception",
            "failed", "errno", "command exited with code",
            "no such file", "permission denied", "timeout",
            "[blocked by middleware",
        )
        return any(lower.startswith(p) for p in error_prefixes)

    def _check_ping_pong(self, history: list[str], sid: str) -> str | None:
        """Detect A→B→A→B alternating pattern in tool name history.

        Returns a warning/hard-stop message if the pattern repeats
        >= ping_pong_threshold times, None otherwise.
        """
        if len(history) < self.ping_pong_threshold:
            return None

        tail = history[-self.ping_pong_threshold:]
        # Check if the tail is a perfect A→B alternation
        if len(set(tail)) == 2:
            a, b = sorted(set(tail))
            pattern = f"{a} → {b}"
            expected = [a if i % 2 == 0 else b for i in range(self.ping_pong_threshold)]
            if tail == expected or tail == list(reversed(expected)):
                warned = self._error_warned.get(sid, set())
                pp_key = f"_ping_pong_{a}_{b}"
                if pp_key not in warned:
                    warned.add(pp_key)
                    self._error_warned[sid] = warned
                    msg = _PING_PONG_MSG.format(
                        pattern=pattern, count=self.ping_pong_threshold
                    )
                    logger.warning(
                        "Ping-pong detected: session=%s pattern=%s",
                        sid, pattern,
                    )
                    return msg
                # Already warned — hard stop on second detection
                return (
                    f"[FORCED STOP] Ping-pong loop {pattern} persists. "
                    f"Producing final answer."
                )
        return None

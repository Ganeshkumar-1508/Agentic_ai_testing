"""Pruning and boundary-alignment utilities for context compression.

What lives here:
  * Tool result summarisation (`summarize_tool_result`) — replaces large
    tool outputs with informative 1-line descriptions per tool name.
  * Tool result pruning (`prune_old_tool_results`) — cheap pre-pass that
    deduplicates identical results, replaces old results with summaries,
    and shrinks long tool-call arguments.  No LLM call.
  * Tool-call / tool-result pair integrity (`sanitize_tool_pairs`) —
    removes orphan results, inserts stubs for orphan calls.
  * Boundary alignment (`align_boundary_forward`, `align_boundary_backward`,
    `protect_head_size`, `find_last_user_message_idx`,
    `ensure_last_user_message_in_tail`) — keeps the head/tail/cut
    boundaries on clean message boundaries, never splitting a
    tool_call/result group or losing the last user message to compression.

Why pure functions: every helper here is also called from the agent
loop in unit tests, and from the main `ContextCompressor.compress()`
orchestrator. Keeping them stateless makes the compression pipeline
reproducible and testable.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Tuple

from harness.context_compressor.content import (
    CHARS_PER_TOKEN,
    content_length_for_budget,
    content_text_for_contains,
    append_text_to_content,
    strip_image_parts_from_parts,
    truncate_tool_call_args_json,
)


__all__ = [
    "summarize_tool_result",
    "prune_old_tool_results",
    "sanitize_tool_pairs",
    "align_boundary_forward",
    "align_boundary_backward",
    "protect_head_size",
    "find_last_user_message_idx",
    "ensure_last_user_message_in_tail",
    "PRUNED_TOOL_PLACEHOLDER",
]


logger = logging.getLogger(__name__)


# Placeholder used when pruning old tool results
PRUNED_TOOL_PLACEHOLDER = "[Old tool output cleared to save context space]"


def summarize_tool_result(tool_name: str, tool_args: str, tool_content: str) -> str:
    """Create an informative 1-line summary of a tool call + result.

    Used during the pre-compression pruning pass to replace large tool
    outputs with a short but useful description of what the tool did,
    rather than a generic placeholder that carries zero information.

    Returns strings like::
        [terminal] ran `npm test` -> exit 0, 47 lines output
        [read_file] read config.py from line 1 (1,200 chars)
        [search_files] content search for 'compress' in agent/ -> 12 matches
    """
    try:
        args = json.loads(tool_args) if tool_args else {}
    except (json.JSONDecodeError, TypeError):
        args = {}

    content = tool_content or ""
    content_len = len(content)
    line_count = content.count("\n") + 1 if content.strip() else 0

    if tool_name == "terminal":
        cmd = args.get("command", "")
        if len(cmd) > 80:
            cmd = cmd[:77] + "..."
        exit_match = re.search(r'"exit_code"\s*:\s*(-?\d+)', content)
        exit_code = exit_match.group(1) if exit_match else "?"
        return f"[terminal] ran `{cmd}` -> exit {exit_code}, {line_count} lines output"

    if tool_name == "read_file":
        path = args.get("path", "?")
        offset = args.get("offset", 1)
        return f"[read_file] read {path} from line {offset} ({content_len:,} chars)"

    if tool_name == "write_file":
        path = args.get("path", "?")
        written_lines = args.get("content", "").count("\n") + 1 if args.get("content") else "?"
        return f"[write_file] wrote to {path} ({written_lines} lines)"

    if tool_name == "search_files":
        pattern = args.get("pattern", "?")
        path = args.get("path", ".")
        target = args.get("target", "content")
        match_count = re.search(r'"total_count"\s*:\s*(\d+)', content)
        count = match_count.group(1) if match_count else "?"
        return f"[search_files] {target} search for '{pattern}' in {path} -> {count} matches"

    if tool_name == "patch":
        path = args.get("path", "?")
        mode = args.get("mode", "replace")
        return f"[patch] {mode} in {path} ({content_len:,} chars result)"

    if tool_name in {"browser_navigate", "browser_click", "browser_snapshot",
                     "browser_type", "browser_scroll", "browser_vision"}:
        url = args.get("url", "")
        ref = args.get("ref", "")
        detail = f" {url}" if url else (f" ref={ref}" if ref else "")
        return f"[{tool_name}]{detail} ({content_len:,} chars)"

    if tool_name == "web_search":
        query = args.get("query", "?")
        return f"[web_search] query='{query}' ({content_len:,} chars result)"

    if tool_name == "web_extract":
        urls = args.get("urls", [])
        url_desc = urls[0] if isinstance(urls, list) and urls else "?"
        if isinstance(urls, list) and len(urls) > 1:
            url_desc += f" (+{len(urls) - 1} more)"
        return f"[web_extract] {url_desc} ({content_len:,} chars)"

    if tool_name == "delegate_task":
        goal = args.get("goal", "")
        if len(goal) > 60:
            goal = goal[:57] + "..."
        return f"[delegate_task] '{goal}' ({content_len:,} chars result)"

    if tool_name == "execute_code":
        code_preview = (args.get("code") or "")[:60].replace("\n", " ")
        if len(args.get("code", "")) > 60:
            code_preview += "..."
        return f"[execute_code] `{code_preview}` ({line_count} lines output)"

    if tool_name in {"skill_view", "skills_list", "skill_manage"}:
        name = args.get("name", "?")
        return f"[{tool_name}] name={name} ({content_len:,} chars)"

    if tool_name == "vision_analyze":
        question = args.get("question", "")[:50]
        return f"[vision_analyze] '{question}' ({content_len:,} chars)"

    if tool_name == "memory":
        action = args.get("action", "?")
        target = args.get("target", "?")
        return f"[memory] {action} on {target}"

    if tool_name == "todo":
        return "[todo] updated task list"

    if tool_name == "clarify":
        return "[clarify] asked user a question"

    if tool_name == "text_to_speech":
        return f"[text_to_speech] generated audio ({content_len:,} chars)"

    if tool_name == "cronjob":
        action = args.get("action", "?")
        return f"[cronjob] {action}"

    if tool_name == "process":
        action = args.get("action", "?")
        sid = args.get("session_id", "?")
        return f"[process] {action} session={sid}"

    # Generic fallback
    first_arg = ""
    for k, v in list(args.items())[:2]:
        sv = str(v)[:40]
        first_arg += f" {k}={sv}"
    return f"[{tool_name}]{first_arg} ({content_len:,} chars result)"


# ----------------------------------------------------------------------
# Tool-call / tool-result pair integrity
# ----------------------------------------------------------------------


def _get_tool_call_id(tc) -> str:
    """Extract the call ID from a tool_call entry (dict or SimpleNamespace)."""
    if isinstance(tc, dict):
        return tc.get("call_id", "") or tc.get("id", "") or ""
    return getattr(tc, "call_id", "") or getattr(tc, "id", "") or ""


def sanitize_tool_pairs(
    messages: List[Dict[str, Any]],
    quiet_mode: bool = False,
) -> List[Dict[str, Any]]:
    """Fix orphaned tool_call / tool_result pairs after compression.

    Two failure modes:
    1. A tool *result* references a call_id whose assistant tool_call was
       removed (summarized/truncated).  The API rejects this with
       "No tool call found for function call output with call_id ...".
    2. An assistant message has tool_calls whose results were dropped.
       The API rejects this because every tool_call must be followed by a
       tool result with the matching call_id.

    This method removes orphaned results and inserts stub results for
    orphaned calls so the message list is always well-formed.
    """
    surviving_call_ids: set = set()
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                cid = _get_tool_call_id(tc)
                if cid:
                    surviving_call_ids.add(cid)

    result_call_ids: set = set()
    for msg in messages:
        if msg.get("role") == "tool":
            cid = msg.get("tool_call_id")
            if cid:
                result_call_ids.add(cid)

    # 1. Remove tool results whose call_id has no matching assistant tool_call
    orphaned_results = result_call_ids - surviving_call_ids
    if orphaned_results:
        messages = [
            m for m in messages
            if not (m.get("role") == "tool" and m.get("tool_call_id") in orphaned_results)
        ]
        if not quiet_mode:
            logger.info("Compression sanitizer: removed %d orphaned tool result(s)", len(orphaned_results))

    # 2. Add stub results for assistant tool_calls whose results were dropped
    missing_results = surviving_call_ids - result_call_ids
    if missing_results:
        patched: List[Dict[str, Any]] = []
        for msg in messages:
            patched.append(msg)
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    cid = _get_tool_call_id(tc)
                    if cid in missing_results:
                        patched.append({
                            "role": "tool",
                            "content": "[Result from earlier conversation — see context summary above]",
                            "tool_call_id": cid,
                        })
        messages = patched
        if not quiet_mode:
            logger.info("Compression sanitizer: added %d stub tool result(s)", len(missing_results))

    return messages


# ----------------------------------------------------------------------
# Boundary alignment
# ----------------------------------------------------------------------


def align_boundary_forward(messages: List[Dict[str, Any]], idx: int) -> int:
    """Push a compress-start boundary forward past any orphan tool results.

    If ``messages[idx]`` is a tool result, slide forward until we hit a
    non-tool message so we don't start the summarised region mid-group.
    """
    while idx < len(messages) and messages[idx].get("role") == "tool":
        idx += 1
    return idx


def align_boundary_backward(messages: List[Dict[str, Any]], idx: int) -> int:
    """Pull a compress-end boundary backward to avoid splitting a
    tool_call / result group.

    If the boundary falls in the middle of a tool-result group (i.e.
    there are consecutive tool messages before ``idx``), walk backward
    past all of them to find the parent assistant message.  If found,
    move the boundary before the assistant so the entire
    assistant + tool_results group is included in the summarised region
    rather than being split (which causes silent data loss when
    ``sanitize_tool_pairs`` removes the orphaned tail results).
    """
    if idx <= 0 or idx >= len(messages):
        return idx
    # Walk backward past consecutive tool results
    check = idx - 1
    while check >= 0 and messages[check].get("role") == "tool":
        check -= 1
    # If we landed on the parent assistant with tool_calls, pull the
    # boundary before it so the whole group gets summarised together.
    if check >= 0 and messages[check].get("role") == "assistant" and messages[check].get("tool_calls"):
        idx = check
    return idx


def protect_head_size(messages: List[Dict[str, Any]], protect_first_n: int) -> int:
    """Total count of head messages to protect.

    ``protect_first_n`` is defined as *additional* messages protected
    beyond the system prompt.  The system prompt (if present at index 0)
    is always implicitly protected — it's load-bearing context that
    must never be summarised away.  This keeps semantics stable across
    call paths where the system prompt may or may not be included in
    the ``messages`` list (e.g. the gateway ``/compress`` handler
    strips it before calling compress()).

    Examples:
      protect_first_n=0 → system prompt only (or nothing if no system msg)
      protect_first_n=3 → system + first 3 non-system messages
    """
    head = 0
    if messages and messages[0].get("role") == "system":
        head = 1
    return head + protect_first_n


def find_last_user_message_idx(
    messages: List[Dict[str, Any]], head_end: int
) -> int:
    """Return the index of the last user-role message at or after *head_end*, or -1."""
    for i in range(len(messages) - 1, head_end - 1, -1):
        if messages[i].get("role") == "user":
            return i
    return -1


def ensure_last_user_message_in_tail(
    messages: List[Dict[str, Any]],
    cut_idx: int,
    head_end: int,
    quiet_mode: bool = False,
) -> int:
    """Guarantee the most recent user message is in the protected tail.

    Context compressor bug (#10896): ``align_boundary_backward`` can pull
    ``cut_idx`` past a user message when it tries to keep tool_call/result
    groups together.  If the last user message ends up in the *compressed*
    middle region the LLM summariser writes it into "Pending User Asks",
    but ``SUMMARY_PREFIX`` tells the next model to respond only to user
    messages *after* the summary — so the task effectively disappears from
    the active context, causing the agent to stall, repeat completed work,
    or silently drop the user's latest request.

    Fix: if the last user-role message is not already in the tail
    (``messages[cut_idx:]``), walk ``cut_idx`` back to include it.  We
    then re-align backward one more time to avoid splitting any
    tool_call/result group that immediately precedes the user message.
    """
    last_user_idx = find_last_user_message_idx(messages, head_end)
    if last_user_idx < 0:
        # No user message found beyond head — nothing to anchor.
        return cut_idx

    if last_user_idx >= cut_idx:
        # Already in the tail; nothing to do.
        return cut_idx

    # The last user message is in the middle (compressed) region.
    # Pull cut_idx back to it directly — a user message is already a
    # clean boundary (no tool_call/result splitting risk), so there is no
    # need to call align_boundary_backward here; doing so would
    # unnecessarily pull the cut further back into the preceding
    # assistant + tool_calls group.
    if not quiet_mode:
        logger.debug(
            "Anchoring tail cut to last user message at index %d "
            "(was %d) to prevent active-task loss after compression",
            last_user_idx,
            cut_idx,
        )
    # Safety: never go back into the head region.
    return max(last_user_idx, head_end + 1)


# ----------------------------------------------------------------------
# Tool result pruning
# ----------------------------------------------------------------------


def prune_old_tool_results(
    messages: List[Dict[str, Any]],
    protect_tail_count: int,
    protect_tail_tokens: int | None = None,
    quiet_mode: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """Replace old tool result contents with informative 1-line summaries.

    Instead of a generic placeholder, generates a summary like::
        [terminal] ran `npm test` -> exit 0, 47 lines output
        [read_file] read config.py from line 1 (3,400 chars)

    Also deduplicates identical tool results (e.g. reading the same file
    5x keeps only the newest full copy) and truncates large tool_call
    arguments in assistant messages outside the protected tail.

    Walks backward from the end, protecting the most recent messages that
    fall within ``protect_tail_tokens`` (when provided) OR the last
    ``protect_tail_count`` messages (backward-compatible default).
    When both are given, the token budget takes priority and the message
    count acts as a hard minimum floor.

    Returns (pruned_messages, pruned_count).
    """
    if not messages:
        return messages, 0

    result = [m.copy() for m in messages]
    pruned = 0

    # Build index: tool_call_id -> (tool_name, arguments_json)
    call_id_to_tool: Dict[str, tuple] = {}
    for msg in result:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    cid = tc.get("id", "")
                    fn = tc.get("function", {})
                    call_id_to_tool[cid] = (fn.get("name", "unknown"), fn.get("arguments", ""))
                else:
                    cid = getattr(tc, "id", "") or ""
                    fn = getattr(tc, "function", None)
                    name = getattr(fn, "name", "unknown") if fn else "unknown"
                    args_str = getattr(fn, "arguments", "") if fn else ""
                    call_id_to_tool[cid] = (name, args_str)

    # Determine the prune boundary
    if protect_tail_tokens is not None and protect_tail_tokens > 0:
        # Token-budget approach: walk backward accumulating tokens
        accumulated = 0
        boundary = len(result)
        min_protect = min(protect_tail_count, len(result))
        for i in range(len(result) - 1, -1, -1):
            msg = result[i]
            raw_content = msg.get("content") or ""
            content_len = content_length_for_budget(raw_content)
            msg_tokens = content_len // CHARS_PER_TOKEN + 10
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    args = tc.get("function", {}).get("arguments", "")
                    msg_tokens += len(args) // CHARS_PER_TOKEN
            if accumulated + msg_tokens > protect_tail_tokens and (len(result) - i) >= min_protect:
                boundary = i
                break
            accumulated += msg_tokens
            boundary = i
        # Translate the budget walk into a "protected count", apply the
        # floor in count-space (where `max` reads naturally: protect at
        # least `min_protect` messages or whatever the budget reserved,
        # whichever is more), then convert back to a prune boundary.
        # Doing this in index-space with `max` would invert the direction
        # (smaller index = MORE protected), so a generous budget would
        # silently get truncated back down to `min_protect`.
        budget_protect_count = len(result) - boundary
        protected_count = max(budget_protect_count, min_protect)
        prune_boundary = len(result) - protected_count
    else:
        prune_boundary = len(result) - protect_tail_count

    # Pass 1: Deduplicate identical tool results.
    # When the same file is read multiple times, keep only the most recent
    # full copy and replace older duplicates with a back-reference.
    content_hashes: dict = {}  # hash -> (index, tool_call_id)
    for i in range(len(result) - 1, -1, -1):
        msg = result[i]
        if msg.get("role") != "tool":
            continue
        content = msg.get("content") or ""
        # Multimodal content — dedupe by the text summary if available.
        if isinstance(content, list):
            continue
        if not isinstance(content, str):
            # Multimodal dict envelopes ({_multimodal: True, content: [...]}) and
            # other non-string tool-result shapes can't be hashed/deduped by text.
            continue
        if len(content) < 200:
            continue
        h = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()[:12]
        if h in content_hashes:
            # This is an older duplicate — replace with back-reference
            result[i] = {**msg, "content": "[Duplicate tool output — same content as a more recent call]"}
            pruned += 1
        else:
            content_hashes[h] = (i, msg.get("tool_call_id", "?"))

    # Pass 2: Replace old tool results with informative summaries
    for i in range(prune_boundary):
        msg = result[i]
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        # Multimodal content (base64 screenshots etc.): strip the image
        # payload — keep a lightweight text placeholder in its place.
        # Without this, an old computer_use screenshot (~1MB base64 +
        # ~1500 real tokens) survives every compression pass forever.
        if isinstance(content, list):
            stripped = strip_image_parts_from_parts(content)
            if stripped is not None:
                result[i] = {**msg, "content": stripped}
                pruned += 1
            continue
        if isinstance(content, dict) and content.get("_multimodal"):
            summary = content.get("text_summary") or "[screenshot removed to save context]"
            result[i] = {**msg, "content": f"[screenshot removed] {summary[:200]}"}
            pruned += 1
            continue
        if not isinstance(content, str):
            continue
        if not content or content == PRUNED_TOOL_PLACEHOLDER:
            continue
        # Skip already-deduplicated or previously-summarized results
        if content.startswith("[Duplicate tool output"):
            continue
        # Only prune if the content is substantial (>200 chars)
        if len(content) > 200:
            call_id = msg.get("tool_call_id", "")
            tool_name, tool_args = call_id_to_tool.get(call_id, ("unknown", ""))
            summary = summarize_tool_result(tool_name, tool_args, content)
            result[i] = {**msg, "content": summary}
            pruned += 1

    # Pass 3: Truncate large tool_call arguments in assistant messages
    # outside the protected tail. write_file with 50KB content, for
    # example, survives pruning entirely without this.
    #
    # The shrinking is done inside the parsed JSON structure so the
    # result remains valid JSON — otherwise downstream providers 400
    # on every subsequent turn until the broken call falls out of
    # the window. See ``truncate_tool_call_args_json`` docstring.
    for i in range(prune_boundary):
        msg = result[i]
        if msg.get("role") != "assistant" or not msg.get("tool_calls"):
            continue
        new_tcs = []
        modified = False
        for tc in msg["tool_calls"]:
            if isinstance(tc, dict):
                args = tc.get("function", {}).get("arguments", "")
                if len(args) > 500:
                    new_args = truncate_tool_call_args_json(args)
                    if new_args != args:
                        tc = {**tc, "function": {**tc["function"], "arguments": new_args}}
                        modified = True
            new_tcs.append(tc)
        if modified:
            result[i] = {**msg, "tool_calls": new_tcs}

    return result, pruned

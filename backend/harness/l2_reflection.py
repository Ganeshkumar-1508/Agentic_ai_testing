"""L2 reflection — the "lesson learned" for the next run on the same repo.

Q7-C from the autonomy roadmap. At the end of an orchestrator run,
we call a small LLM with the run's output and ask for a
1-paragraph summary of what worked / what broke. The summary is
written to the per-repo ``memory`` tool (target='memory',
source_kind='success_reflection' or 'failure_reflection') so the
NEXT run on the same repo sees it as the first thing in the
memory block.

This is what makes "fully autonomous" actually compound: the system
gets smarter about a repo with every run, not just within a run.

Implementation choices:
  - Spawned as a fire-and-forget background task (we don't want
    the L2 call to add latency to the API response that the
    dashboard is waiting on).
  - Uses the L2 reflection prompt stored at
    ``.testai/prompts/agents/l2_reflection.txt`` (loaded via
    ``prompt_builder.load_agent_prompt``) so the operator can
    tune the prompt without a code change.
  - Falls back to a default inline prompt if the file is missing.
  - On any failure, logs a warning and moves on — the next run's
    memory block is just the prior runs' reflections; a missing
    reflection is non-fatal.

Reference: hermes-agent `Curator` does the same thing on a
schedule (`agent/curator.py`). We do it inline at run-end so
there's no separate cron / config to maintain.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from harness.memory.db_context import get_db

logger = logging.getLogger(__name__)


_L2_REFLECTION_PROMPT = (
    "You are summarizing a TestAI orchestrator run for the next run "
    "on the same repository. Read the run's output (success or "
    "failure) and produce ONE short paragraph (under 300 words) "
    "covering:\n"
    "  1. What was attempted (1 sentence)\n"
    "  2. Key file paths the next agent should know about\n"
    "  3. Test commands used (e.g. `pytest tests/`, `manage.py test`)\n"
    "  4. Gotchas / things that broke / non-obvious conventions\n"
    "  5. Net result: was the task completed, partially done, or failed\n\n"
    "Write the paragraph in the second person ('You are working on "
    "a repo with...'). Do NOT include tool names, agent IDs, run IDs, "
    "or model names — the next agent should learn about the repo, "
    "not about the prior run's plumbing.\n"
)


def _build_l2_prompt() -> str:
    """Load the operator's L2 reflection prompt, or fall back to the default.

    Reads ``.testai/prompts/agents/l2_reflection.txt`` (same loader
    pattern as the other TestAI roles per `prompt_builder.py`). On
    any I/O error, returns the inline default above.
    """
    try:
        from harness.prompt_builder import load_agent_prompt
        body = load_agent_prompt("l2_reflection")
        if body:
            return body
    except Exception as exc:
        logger.debug("l2_reflection prompt load failed: %s", exc)
    return _L2_REFLECTION_PROMPT


def _truncate_output(output: str, limit: int = 4000) -> str:
    """Cap the input to the LLM so the reflection call stays cheap.

    4k chars ≈ 1k tokens; that's enough to cover the most useful
    parts of a run (the agent's final message + error trace + key
    tool results). Anything longer is a runaway run; the first 4k
    almost always contains the lessons.
    """
    if not output:
        return ""
    if len(output) <= limit:
        return output
    return output[: limit - 100] + "\n\n[truncated — full output was {} chars]".format(len(output))


async def write_l2_reflection(
    *,
    repo_url: str,
    run_id: str,
    output: str,
    success: bool,
) -> bool:
    """Generate + write the L2 reflection. Returns True on success.

    Spawns a background task internally — the caller (orchestrator's
    ``run_single``) can fire-and-forget without awaiting. We expose
    this as ``async`` so the caller *can* await if they want to
    (e.g. in tests).
    """
    try:
        from harness.tools.memory_tool import MemoryTool

        db = get_db()
        if db is None:
            return False
        
        # Use shared LLM router if available
        from harness.api.state import get_llm
        llm = get_llm()
        if llm is None:
            # Fallback: create fresh router and configure from DB
            try:
                from harness.llm import LLMRouter
                llm = LLMRouter()
                try:
                    rows = await db.fetch(
                        "SELECT provider, config FROM provider_configs "
                        "WHERE config->>'enabled' = 'true' OR config->>'enabled' IS NULL"
                    )
                    if rows:
                        settings = []
                        for r in rows:
                            cfg = r["config"]
                            if isinstance(cfg, str):
                                import json as _j
                                cfg = _j.loads(cfg)
                            settings.append({
                                "provider": r["provider"],
                                "model": cfg.get("model", ""),
                                "api_key": cfg.get("api_key", ""),
                                "base_url": cfg.get("base_url", ""),
                                "api_mode": cfg.get("api_mode", "openai"),
                                "enabled": cfg.get("enabled", True),
                            })
                        if settings:
                            llm.configure(settings)
                except Exception as e:
                    logger.warning("Failed to configure LLM from DB: %s", e)
            except Exception:
                llm = None

        if llm is None:
            return False

        prompt = _build_l2_prompt()
        user_msg = (
            f"REPO: {repo_url}\n"
            f"RUN_ID: {run_id}\n"
            f"SUCCESS: {success}\n\n"
            f"OUTPUT (truncated to 4k chars):\n"
            f"{_truncate_output(output)}\n"
        )
        try:
            from harness.llm import ChatMessage
            response = await llm.chat([
                ChatMessage(role="system", content=prompt),
                ChatMessage(role="user", content=user_msg),
            ])
            text = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.warning("l2_reflection LLM call failed: %s", exc)
            return False

        text = (text or "").strip()
        if not text:
            return False
        # Write to the per-repo memory tool. We invoke the tool
        # directly (not via the registry) so this works even when
        # no agent is running.
        tool = MemoryTool()
        result = await tool.run(
            action="add",
            target="memory",
            text=text,
            repo=repo_url,
            source_kind="success_reflection" if success else "failure_reflection",
            confidence=0.7,
        )
        if hasattr(result, "success") and not result.success:
            logger.debug("l2_reflection: memory tool rejected write: %s", result.error)
            return False
        logger.info(
            "l2_reflection written repo=%s run=%s chars=%d",
            repo_url, run_id, len(text),
        )
        return True
    except Exception as exc:
        logger.warning("l2_reflection unexpected error: %s", exc)
        return False


def schedule_l2_reflection(
    *,
    repo_url: str,
    run_id: str,
    output: str,
    success: bool,
) -> None:
    """Fire-and-forget wrapper used by the orchestrator.

    Creates an asyncio task; if there's no running loop (sync
    path), logs a debug and returns without raising. The task is
    intentionally not awaited; the orchestrator's HTTP response
    returns immediately so the dashboard unblocks.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if loop.is_running():
        try:
            asyncio.create_task(
                write_l2_reflection(
                    repo_url=repo_url, run_id=run_id,
                    output=output, success=success,
                )
            )
        except RuntimeError:
            pass

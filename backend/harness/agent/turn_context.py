"""Per-turn prologue for ``Agent.run_stream``.

Extracted from ``harness/agent/agent.py`` as part of the god-file
decomposition campaign. ``run_stream`` opened with ~50 lines of
straight-line setup before the tool-calling loop started: agent_id
generation, dispatcher init, context manager scope, message init,
tool schema fetch, checkpoint resume, AgentStarted event emit, and
iteration-budget reset. All of that is *prologue* — runs once per
turn, has no back-references into the loop, and produces a fixed set
of values the loop then consumes.

``TurnContext`` captures those values; ``build_turn_context``
performs the setup and returns one. ``run_stream`` is left to
unpack the context and run the loop. The builder still mutates
``agent`` (counters, dispatcher, cached system prompt) — those
side effects are the point. The ``TurnContext`` only carries the
locals the loop reads back.

Pattern from hermes-agent ``agent/turn_context.py`` (438 lines, MIT).
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Callable

from harness.core.events import (
    AgentStarted,
    StatusEvent,
    StreamEvent,
)

if TYPE_CHECKING:
    from harness.agent.agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class TurnContext:
    """Values produced by the turn prologue and consumed by the turn loop."""
    agent_id: str
    user_input: str
    resume_turn: int = 0
    cancelled: bool = False
    # When True, the loop should append a prompt-level hint reminding
    # the model to consider using the ``memory`` tool for this turn. Set by the
    # 30-turn nudge in :func:`build_turn_context` when the counter
    # crosses ``Agent._memory_nudge_interval``. The hint is a prompt
    # append, not a message rewrite — the prompt cache stays valid.
    should_review_memory: bool = False


@asynccontextmanager
async def agent_scope(agent_id: str) -> AsyncIterator[None]:
    """Context manager wrapper around ``harness.context.manager.scope``.

    Imported lazily to avoid a circular import — ``context.manager`` is
    set up in ``harness/__init__.py`` after the agent package loads.
    """
    mgr = __import__("harness.context", fromlist=["manager"]).manager
    async with mgr.scope(agent_id=agent_id):
        yield


async def build_turn_context(
    agent: "Agent",
    user_input: str,
    agent_id: str,
) -> TurnContext:
    """Run the per-turn prologue. Mutates ``agent``; returns the loop's inputs.

    Steps (in order):
      1. Init the tool dispatcher.
      2. Init messages via ``agent._init_messages``.
      3. Compute tool schemas (read-only lookup on the registry).
      4. Attempt checkpoint resume; populate ``self._messages`` and
         capture ``resume_turn`` on success.
      5. Reset the iteration budget for this turn.
      6. Emit ``AgentStarted`` so the bus + listeners know the turn began.

    Returns the ``TurnContext`` the loop reads back. The caller is
    responsible for opening the context-manager scope (passing the
    same ``agent_id``) and yielding the ``AgentStarted`` event to
    the SSE stream.
    """
    agent._dispatcher = agent._make_dispatcher()
    await agent._init_messages(user_input)
    schemas = agent._get_tool_schemas()
    if schemas:
        print(f"DEBUG: Agent has {len(schemas)} tool schemas; first={schemas[0].get('function', {}).get('name', '?')}")
    else:
        print("DEBUG: Agent has 0 tool schemas")

    resume_turn = 0
    try:
        agent._init_checkpoint_mgr()
        if agent._checkpoint_mgr:
            latest = await agent._checkpoint_mgr.latest_checkpoint()
            if latest and (latest.get("turn_count") or 0) > 0:
                snapshot = latest.get("messages_snapshot") or []
                if isinstance(snapshot, str):
                    try:
                        import json
                        snapshot = json.loads(snapshot)
                    except (json.JSONDecodeError, TypeError):
                        snapshot = []
                if snapshot:
                    from harness.llm import ChatMessage
                    agent._messages = [
                        ChatMessage(
                            role=m.get("role", "user") if isinstance(m, dict) else getattr(m, "role", "user"),
                            content=m.get("content", "") if isinstance(m, dict) else getattr(m, "content", ""),
                        )
                        for m in snapshot
                    ]
                    resume_turn = int(latest.get("turn_count") or 0)
                    ev_status = StatusEvent(
                        message=f"Resumed session from turn {resume_turn} ({len(agent._messages)} messages)",
                    )
                    await agent._event_bus.emit(ev_status)
                    logger.info(
                        "build_turn_context: resumed session=%s from turn=%d messages=%d",
                        agent.session_id, resume_turn, len(agent._messages),
                    )
    except Exception as ckpt_exc:
        logger.warning("Checkpoint resume failed (continuing fresh): %s", ckpt_exc)

    agent.iteration_budget.reset(max_total=agent.max_tool_rounds)

    should_review_memory = check_memory_nudge(agent)

    ev = AgentStarted(
        agent_id=agent_id, input=user_input[:200],
        model=getattr(agent, "model_override", None) or "default",
        mode=agent.mode,
    )
    await agent._emit(ev)

    return TurnContext(
        agent_id=agent_id,
        user_input=user_input,
        resume_turn=resume_turn,
        should_review_memory=should_review_memory,
    )


def check_memory_nudge(agent: "Agent") -> bool:
    """Hermes-style 30-turn memory nudge.

    Increments ``agent._turns_since_memory`` and returns ``True``
    when the counter crosses ``agent._memory_nudge_interval``. The
    caller (``build_turn_context``) sets the returned value on
    :class:`TurnContext.should_review_memory` so the main loop
    appends a prompt-only hint.

    The nudge never mutates the message list — only a counter on
    the agent instance — so the prompt cache stays valid. Setting
    ``_memory_nudge_interval = 0`` disables the nudge.

    Returned: ``True`` if the nudge fired this turn, ``False`` otherwise.
    """
    interval = int(getattr(agent, "_memory_nudge_interval", 30) or 0)
    if interval <= 0:
        return False
    agent._turns_since_memory = int(getattr(agent, "_turns_since_memory", 0) or 0) + 1
    if agent._turns_since_memory >= interval:
        agent._turns_since_memory = 0
        logger.debug(
            "check_memory_nudge: fired (interval=%d)", interval,
        )
        return True
    return False


async def emit_startup_event(agent: "Agent", ctx: TurnContext) -> StreamEvent:
    """Yield the AgentStarted event from the turn prologue to the SSE stream.

    Helper that lets ``run_stream`` yield the same event the prologue
    emitted, without re-creating it. Returns the event object the
    caller should yield.
    """
    return AgentStarted(
        agent_id=ctx.agent_id, input=ctx.user_input[:200],
        model=getattr(agent, "model_override", None) or "default",
        mode=agent.mode,
    )


__all__ = [
    "TurnContext",
    "agent_scope",
    "build_turn_context",
    "check_memory_nudge",
    "emit_startup_event",
]

"""Post-loop turn finalization for ``Agent.run_stream``.

Bundles the post-loop side effects (final event emit, future
trajectory save + session persist) into a single function with the
**never-raise** invariant: every side effect is independently
guarded with its own try/except. Failures land in
``result["cleanup_errors"]`` but the AgentCompleted event is still
yielded so the SSE consumer sees the turn wrap up.

Pattern from hermes-agent ``agent/turn_finalizer.py`` (485 lines, MIT).
"""
from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, Any

from harness.core.events import AgentCompleted, StreamEvent

if TYPE_CHECKING:
    from harness.agent.agent import Agent

logger = logging.getLogger(__name__)


class TurnFinalizerResult:
    """Result of the post-loop finalization.

    Carries the ``cleanup_errors`` list (each entry is a
    ``(label, exc_repr)`` tuple) so the caller can surface them
    in the result dict / SSE completion frame.
    """

    __slots__ = ("cleanup_errors", "agent_completed_event", "trajectory_saved")

    def __init__(self) -> None:
        self.cleanup_errors: list[tuple[str, str]] = []
        self.agent_completed_event: AgentCompleted | None = None
        self.trajectory_saved: bool = False

    def record(self, label: str, exc: BaseException) -> None:
        """Append a cleanup error without raising."""
        self.cleanup_errors.append((label, f"{type(exc).__name__}: {exc}"))
        logger.warning("turn_finalizer[%s]: %s: %s", label, type(exc).__name__, exc)


def finalize_turn(
    agent: "Agent",
    *,
    agent_id: str,
    rounds_completed: int,
    cancelled: bool,
    max_rounds_reached: bool,
) -> TurnFinalizerResult:
    """Run the post-loop finalization. Never raises.

    Currently bundles:
      * Trajectory save (no-op until the trajectory-recording
        subsystem lands; the slot is here so the wiring point is
        defined).
      * Session persist (delegated to ``agent._persist_session``
        if present; failures swallowed).
      * ``AgentCompleted`` event assembly and emit.

    The result carries ``cleanup_errors`` so the caller can attach
    them to the result dict / SSE completion frame.
    """
    result = TurnFinalizerResult()

    try:
        if getattr(agent, "_save_trajectory", None) is not None:
            saved = agent._save_trajectory()
            if saved:
                result.trajectory_saved = True
    except BaseException as exc:  # noqa: BLE001
        result.record("trajectory_save", exc)

    try:
        persist = getattr(agent, "_persist_session", None)
        if persist is not None:
            persist()
    except BaseException as exc:  # noqa: BLE001
        result.record("session_persist", exc)

    try:
        output_preview = ""
        last = agent._messages[-1] if agent._messages else None
        if last is not None:
            output_preview = (getattr(last, "content", "") or "")[:200]
        if not output_preview and max_rounds_reached:
            output_preview = "Max tool rounds reached."
        ev_max = AgentCompleted(
            agent_id=agent_id,
            output_preview=output_preview,
            rounds=rounds_completed,
            cancelled=cancelled,
        )
        result.agent_completed_event = ev_max
    except BaseException as exc:  # noqa: BLE001
        result.record("agent_completed_assembly", exc)
        ev_max = AgentCompleted(
            agent_id=agent_id, output_preview="",
            rounds=rounds_completed, cancelled=cancelled,
        )
        result.agent_completed_event = ev_max

    return result


__all__ = ["TurnFinalizerResult", "finalize_turn"]

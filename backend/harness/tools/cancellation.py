"""Cascading cancellation for subagent delegation tree."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time


logger = logging.getLogger(__name__)

# --- Cancellation ---
CANCEL_GRACE_PERIOD_SECONDS = 5.0


@dataclasses.dataclass
class CancellationNode:
    """One node in the cancellation tree."""
    subagent_id: str
    parent_id: str | None
    children_ids: list[str] = dataclasses.field(default_factory=list)
    cancel_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    cancelled: bool = False
    cancel_reason: str = ""
    cancelled_at: float | None = None


class CancellationTree:
    """Tracks parent → child relationships for cascading cancellation.

    Calling `cancel(subagent_id, reason)` cancels that node and recursively
    cancels all descendants, signalling each via an asyncio.Event the agent
    loop can poll. The agent has `grace_period_seconds` to clean up before
    being force-cancelled.
    """

    def __init__(self, grace_period_seconds: float = CANCEL_GRACE_PERIOD_SECONDS) -> None:
        self._nodes: dict[str, CancellationNode] = {}
        self._lock = asyncio.Lock()
        self.grace_period_seconds = grace_period_seconds

    async def register(
        self, subagent_id: str, parent_id: str | None = None,
    ) -> CancellationNode:
        async with self._lock:
            node = self._nodes.get(subagent_id)
            if node is None:
                node = CancellationNode(
                    subagent_id=subagent_id, parent_id=parent_id,
                )
                self._nodes[subagent_id] = node
            if parent_id:
                parent = self._nodes.get(parent_id)
                if parent is not None and subagent_id not in parent.children_ids:
                    parent.children_ids.append(subagent_id)
            return node

    def get(self, subagent_id: str) -> CancellationNode | None:
        return self._nodes.get(subagent_id)

    def is_cancelled(self, subagent_id: str) -> bool:
        node = self._nodes.get(subagent_id)
        return node is not None and node.cancelled

    async def cancel(
        self,
        subagent_id: str,
        reason: str = "parent cancelled",
    ) -> list[str]:
        """Cancel this node + all descendants. Returns IDs that were cancelled."""
        cancelled: list[str] = []
        async with self._lock:
            node = self._nodes.get(subagent_id)
            if node is None:
                return cancelled
            to_visit = [node]
            while to_visit:
                cur = to_visit.pop()
                if cur.cancelled:
                    continue
                cur.cancelled = True
                cur.cancel_reason = reason
                cur.cancelled_at = time.time()
                cur.cancel_event.set()
                cancelled.append(cur.subagent_id)
                for child_id in cur.children_ids:
                    child = self._nodes.get(child_id)
                    if child is not None and not child.cancelled:
                        to_visit.append(child)
        logger.info(
            "cancellation.cascade root=%s cancelled=%d reason=%s",
            subagent_id, len(cancelled), reason,
        )
        return cancelled

    def cleanup(self, subagent_id: str) -> None:
        """Remove a node (called after agent exits)."""
        node = self._nodes.pop(subagent_id, None)
        if node and node.parent_id:
            parent = self._nodes.get(node.parent_id)
            if parent and subagent_id in parent.children_ids:
                parent.children_ids.remove(subagent_id)


_cancellation_tree = CancellationTree()


def get_cancellation_tree() -> CancellationTree:
    return _cancellation_tree

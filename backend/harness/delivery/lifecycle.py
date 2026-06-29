from __future__ import annotations

import logging
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)

_MAX_CACHE_SIZE = 128
_IDLE_TTL_SECONDS = 3600.0


class AgentLifecycle:
    """Caches agent instances per session with TTL eviction.

    Pattern extracted from gateway/run.py GatewayRunner. Agents are
    kept alive across turns within a session and evicted when idle
    past the TTL or when the cache exceeds max_size.
    """

    def __init__(self, max_size: int = _MAX_CACHE_SIZE, idle_ttl: float = _IDLE_TTL_SECONDS):
        self.max_size = max_size
        self.idle_ttl = idle_ttl
        self._agents: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, session_id: str) -> object | None:
        entry = self._agents.get(session_id)
        if entry is None:
            return None
        ts, agent = entry
        if time.monotonic() - ts > self.idle_ttl:
            self._agents.pop(session_id)
            logger.info("Evicted idle agent for session %s", session_id)
            return None
        self._agents.move_to_end(session_id)
        self._agents[session_id] = (time.monotonic(), agent)
        return agent

    def set(self, session_id: str, agent: object) -> None:
        self._agents[session_id] = (time.monotonic(), agent)
        self._enforce_cap()

    def remove(self, session_id: str) -> None:
        self._agents.pop(session_id, None)

    def evict_idle(self) -> int:
        now = time.monotonic()
        stale = [sid for sid, (ts, _) in self._agents.items() if now - ts > self.idle_ttl]
        for sid in stale:
            self._agents.pop(sid)
        if stale:
            logger.info("Evicted %d idle agent(s)", len(stale))
        return len(stale)

    def active_count(self) -> int:
        return len(self._agents)

    def _enforce_cap(self) -> None:
        while len(self._agents) > self.max_size:
            sid, _ = self._agents.popitem(last=False)
            logger.debug("Evicted oldest agent %s (cache at capacity)", sid)

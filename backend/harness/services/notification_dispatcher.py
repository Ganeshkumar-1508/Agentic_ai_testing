"""NotificationDispatcher &mdash; per-run status notification formatting + delivery.

Wire of C03 (orchestrator decomposition), Phase 3. The original
``harness.orchestrator.OrchestratorEngine._send_notification``
was a 30-LOC method that:

1. formatted a multi-line content string (``Orchestration {status}\n...``)
2. queried the DB for ``notification_prefs`` matching ``run:{status}``
3. delivered to each matching target via ``DeliveryRouter``

The work has a clear seam: ``format`` is pure
``(session_id, repo_url, status, summary) -> str`` and
``dispatch`` is the async orchestrator that combines format +
DB query + delivery. Both are static/staticmethod, no class
state, so the call site (a method on
``OrchestratorEngine``) becomes a 3-line thin delegate.

This module mirrors the pattern of
:mod:`harness.services.tier_policy` and
:mod:`harness.services.sandbox_bootstrap`: the engine
stops impersonating each collaborator and asks the
sibling module for the answer.

Per :mod:`CONTEXT.md` glossary:
- **NotificationDispatcher** &mdash; this module
- **format** &mdash; pure, returns the multi-line content string
- **dispatch** &mdash; async, full pipeline (format + DB query + delivery)
- **EXTERNAL_URL** &mdash; the env var the formatter reads for the
  dashboard deep-link; defaults to ``http://localhost:3000``
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Per-run status notification formatting + delivery.

    Stateless; the methods are static. The engine still owns
    the ``session_id`` and the call cadence (3 places in
    ``run_single``'s completion / failure / timeout branches);
    the dispatcher just formats and delivers.
    """

    #: Default dashboard base URL. Overridden by the
    #: ``EXTERNAL_URL`` env var (set in production to the
    #: real hostname).
    DEFAULT_BASE_URL: ClassVar[str] = "http://localhost:3000"

    #: The event-type prefix the formatter writes into the
    #: ``notification_prefs.events`` JSONB array. The DB
    #: query in :meth:`dispatch` filters on
    #: ``run:{status}`` so a user with a Slack channel
    #: subscribed to ``run:failed`` only gets failure
    #: notifications, not completion ones.
    EVENT_PREFIX: ClassVar[str] = "run:"

    #: Max characters of the ``session_id`` echoed in the
    #: notification body. 12 is the first three groups of a
    #: UUID, which is unique enough for a chat reply and short
    #: enough to fit a Slack line.
    SESSION_ID_ECHO_CHARS: ClassVar[int] = 12

    # ------------------------------------------------------------------
    # Pure: status + summary &rarr; content string. No DB, no I/O.
    # ------------------------------------------------------------------

    @staticmethod
    def format(
        session_id: str,
        repo_url: str,
        status: str,
        summary: str,
        base_url: str | None = None,
    ) -> str:
        """Build the multi-line notification content.

        Returns the 5-line block used for both Slack/Discord
        posts and email subjects. The dashboard deep-link is
        always the last line so a user can click through
        without parsing the body.

        ``base_url`` defaults to the ``EXTERNAL_URL`` env var
        (or :attr:`DEFAULT_BASE_URL` if unset). Tests can pass
        an explicit value to keep the output deterministic.
        """
        url = base_url or os.environ.get("EXTERNAL_URL") or NotificationDispatcher.DEFAULT_BASE_URL
        return (
            f"Orchestration {status}\n"
            f"Repo: {repo_url}\n"
            f"Session: {session_id[:NotificationDispatcher.SESSION_ID_ECHO_CHARS]}\n"
            f"Status: {summary}\n"
            f"View: {url}/pipeline?session_id={session_id}"
        )

    # ------------------------------------------------------------------
    # Async: shell out to DB + DeliveryRouter. Only this method
    # touches I/O; the formatter is pure.
    # ------------------------------------------------------------------

    @staticmethod
    async def dispatch(
        session_id: str,
        repo_url: str,
        status: str,
        summary: str,
        db: Any = None,
        channels: list[str] | None = None,
    ) -> None:
        """Format the notification, find matching prefs, deliver to each target.

        If ``channels`` is provided (from Advanced Config ``notification_channels``),
        only those channels are used. Otherwise, all enabled prefs matching
        the run:{status} event are used.

        Returns ``None`` (fire-and-forget). On any error &mdash;
        no DB, no prefs, delivery failure &mdash; the call
        logs a warning and returns; notification delivery is
        never allowed to break the orchestration run.

        Args:
            session_id: the run's session id (UUID)
            repo_url: the repo the run targeted (for the body)
            status: one of ``"completed"``, ``"failed"``,
                ``"timeout"``; used both in the body and as
                the ``run:{status}`` event-type filter
            summary: human-readable one-liner the engine
                produces (e.g. ``"5/5 tasks done in 47s"``)
            db: the asyncpg/Postgres connection; passed in so
                the engine can use its existing ``get_db()``
                handle. If ``None``, dispatch is a no-op.
        """
        if db is None:
            logger.debug(
                "NotificationDispatcher.dispatch: no db handle; "
                "skipping run:%s notification for session=%s",
                status, session_id[:NotificationDispatcher.SESSION_ID_ECHO_CHARS],
            )
            return

        content = NotificationDispatcher.format(session_id, repo_url, status, summary)
        event = f"{NotificationDispatcher.EVENT_PREFIX}{status}"

        try:
            from harness.delivery.router import DeliveryRouter
            from harness.delivery.adapters.base import DeliveryTarget
            router = DeliveryRouter(db=db)
            if channels:
                placeholders = ", ".join(f"${i+2}" for i in range(len(channels)))
                rows = await db.fetch(
                    f"SELECT channel, target FROM notification_prefs "
                    f"WHERE enabled = true AND CAST(events AS jsonb) @> CAST($1 AS jsonb) AND channel IN ({placeholders})",
                    json.dumps([event]), *channels,
                )
            else:
                rows = await db.fetch(
                    "SELECT channel, target FROM notification_prefs "
                    "WHERE enabled = true AND CAST(events AS jsonb) @> CAST($1 AS jsonb)",
                    json.dumps([event]),
                )
            for row in rows:
                t = row["target"] or ""
                channel = row["channel"]
                # For email channels, use the channel as platform and target as chat_id
                if channel == "email" and "@" in t:
                    target = DeliveryTarget(platform=channel, chat_id=t)
                elif t:
                    target = DeliveryTarget.parse(t)
                else:
                    target = DeliveryTarget(platform=channel)
                await router.deliver(content, [target])
        except Exception as exc:
            logger.warning(
                "Failed to send run:%s notification for session=%s: %s",
                status, session_id[:NotificationDispatcher.SESSION_ID_ECHO_CHARS], exc,
            )

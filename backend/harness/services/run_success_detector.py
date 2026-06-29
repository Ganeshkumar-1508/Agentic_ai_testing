"""Run-success detector — strategy-pattern seam for the orchestrator.

Adapters (one strategy per failure mode):
  - :class:`StringMatch` — pattern-detect error strings in the result.
  - :class:`VerdictStrategy` — read per-tool-call ``rca_verdict`` from
    ``context["db"]`` and the session's agent_artifacts. If ANY tool
    returned DEFECT, the run failed; if only FLAKY, passed with
    warnings; if all OK, passed clean.
  - :class:`QualityScore` — future: consult project-level quality trend.
  - :class:`EvidenceMatch` — future: verify run produced L0 evidence.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class SuccessDetector(Protocol):
    """A strategy that votes on whether a run succeeded."""

    name: str

    def detect(self, result: Any, *, context: dict[str, Any] | None = None) -> tuple[bool, str]:
        """Return ``(is_failure, reason)``.

        ``is_failure=True`` means this strategy flagged the result.
        The detector combines the votes — see :class:`RunSuccessDetector`.
        """
        ...


class StringMatch:
    """Detect failure by pattern-matching known error strings in the result.

    Mirrors the original ``_derive_run_success`` logic exactly. The
    patterns are the ones the orchestrator already knew about; the
    seam just makes them addressable.
    """

    name = "string_match"

    _PATTERNS = (
        ("max_tool_rounds", "max tool rounds"),
        ("max_tool_rounds", "Max tool rounds reached"),
        ("coordinator_failed", '"success": false'),
    )

    def detect(self, result: Any, *, context: dict[str, Any] | None = None) -> tuple[bool, str]:
        # Object shape: ``result.success is False`` is the explicit
        # failure signal. The orchestrator's delegate_task returns
        # an object on a normal completion (success=True) and a
        # string on the max-rounds exit path. If the object says
        # failure, it's a real failure regardless of the text.
        if result is not None and not isinstance(result, str):
            if getattr(result, "success", None) is False:
                return True, "coordinator_failed"
        text = ""
        if isinstance(result, str):
            text = result
        else:
            text = str(getattr(result, "output", "") or "")
        lowered = text.lower()
        for reason, needle in self._PATTERNS:
            if needle.lower() in lowered:
                return True, reason
        return False, "ok"


class QualityScore:
    """Caveat from Greptile: don't assume model-agnosticism is free.

    Not wired yet &mdash; placeholder so the seam is explicit. When
    the harness's project-level quality trend goes the wrong way,
    a single "string-match success" is suspect. The wiring will
    consult :func:`harness.quality_score.compute_quality_score` and
    return ``True, "quality_trend_degraded"`` when the trend is
    dropping.
    """

    name = "quality_score"

    def detect(self, result: Any, *, context: dict[str, Any] | None = None) -> tuple[bool, str]:
        # Future: read ``context["db"]`` and consult
        # ``compute_quality_score(db, project_id=...)``. For now,
        # never flags.
        return False, "ok"


class EvidenceMatch:
    """F6 seam: a run with no tool-call evidence is suspect.

    Not wired yet &mdash; placeholder. When the orchestrator has
    access to the session's evidence set (via
    :class:`harness.evidence.EvidenceBundler`), a run that produced
    zero tool-call artifacts is flagged.
    """

    name = "evidence_match"

    def detect(self, result: Any, *, context: dict[str, Any] | None = None) -> tuple[bool, str]:
        # Future: read ``context["evidence"]`` and assert at least
        # one tool_call artifact was captured. For now, never flags.
        return False, "ok"


class VerdictStrategy:
    """C5: read per-tool-call rca_verdict from the session's artifacts.

    Requires ``context["session_id"]`` and ``context["db"]``.
    If ANY tool call returned DEFECT, the run failed.
    If only FLAKY (no DEFECT), the run passed with warnings.
    If all OK/UNKNOWN, the run passed clean.

    Wire this before StringMatch so verdict takes priority over
    raw string matching. Wire it after StringMatch if you prefer
    the legacy behaviour.
    """

    name = "verdict_strategy"

    def detect(self, result: Any, *, context: dict[str, Any] | None = None) -> tuple[bool, str]:
        if not context:
            return False, "ok"
        session_id = context.get("session_id", "")
        db = context.get("db")
        if not session_id or not db:
            return False, "ok"

        try:
            import json
            rows = db.fetch(
                "SELECT payload::text FROM agent_artifacts "
                "WHERE session_id = $1 AND kind = 'tool_call' "
                "ORDER BY id ASC",
                session_id,
            )
        except Exception:
            return False, "ok"

        if not rows:
            return False, "ok"

        has_defect = False
        has_flaky = False
        for r in (rows or []):
            try:
                payload = r["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                verdict_data = (payload or {}).get("rca_verdict") or {}
                verdict = str(verdict_data.get("verdict", "") or "")
                if verdict == "defect":
                    has_defect = True
                elif verdict == "flaky":
                    has_flaky = True
            except Exception:
                continue

        if has_defect:
            return True, "run_has_defects"
        if has_flaky:
            return False, "run_has_flakes_only"
        return False, "ok"


class RunSuccessDetector:
    """Combines a list of strategies and returns the first failure.

    Today: ``[StringMatch()]``. Tomorrow: ``[StringMatch(), QualityScore(),
    EvidenceMatch()]``. New strategies are added by appending to
    ``self.strategies``; the dispatcher and the orchestrator don't
    change.
    """

    def __init__(self, strategies: list[SuccessDetector] | None = None) -> None:
        self.strategies: list[SuccessDetector] = list(
            strategies if strategies is not None else [
                StringMatch(), VerdictStrategy(),
            ]
        )

    def detect(self, result: Any, *, context: dict[str, Any] | None = None) -> tuple[bool, str]:
        for strat in self.strategies:
            try:
                flagged, reason = strat.detect(result, context=context)
                if flagged:
                    return True, reason
            except Exception as exc:
                logger.debug("detector %s raised: %s", getattr(strat, "name", strat), exc)
        return False, "ok"

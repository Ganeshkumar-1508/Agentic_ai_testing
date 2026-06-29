"""Self-healing tool exposed to agents.

Tool:
  - attempt_heal — analyze a failure and suggest alternative locators

Auto-registered into the global ``registry`` on import and assigned
to the ``healing`` toolset.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


def _resolve_db() -> Any | None:
    """Best-effort: get the app-wide async db pool from the running process.

    Tools are constructed lazily and the db handle is registered into
    the process via ``harness.api.deps.set_db``. If it's not yet set,
    we return ``None`` and the tool reports a clean error.
    """
    try:
        # Imported lazily to avoid circular imports at module load.
        from harness.api.deps import get_db_pool  # type: ignore

        return get_db_pool()
    except Exception:
        return None


class AttemptHealTool(BaseTool):
    name = "attempt_heal"
    description = (
        "Analyze a failing test and suggest alternative locators. "
        "Returns the suggested locator, confidence score, and a short "
        "rationale. Does NOT mutate the test file — use apply_patch "
        "or edit for that. Inputs: test_name (str), error (str), "
        "run_id (str, optional), locator (str, optional — the original "
        "locator that failed)."
    )
    capabilities = ["can_read_fs", "can_analyze_failure"]

    async def run(
        self,
        test_name: str,
        error: str = "",
        run_id: str = "",
        locator: str = "",
        **_extra: Any,
    ) -> ToolResult:
        try:
            db = _resolve_db()
            if db is None:
                return ToolResult(
                    success=False,
                    output="DB pool not initialised. attempt_heal needs a running backend.",
                    error="no_db",
                )

            # Prefer the canonical harness function when available; fall
            # back to a simple local heuristic if the module is missing
            # (keeps the tool usable even on a partial install).
            try:
                from harness.self_healing import attempt_heal  # type: ignore

                result = await attempt_heal(db, test_name, error, run_id, locator)
                return ToolResult(success=True, output=str(result), data=result if isinstance(result, dict) else None)
            except ModuleNotFoundError:
                # Local fallback: return a structured "no-suggestion" result.
                return ToolResult(
                    success=True,
                    output=(
                        f"No automatic locator suggestion available for {test_name!r}. "
                        f"Original locator: {locator!r}. Error snippet: "
                        f"{(error or '')[:200]!r}"
                    ),
                    data={
                        "test_name": test_name,
                        "suggested_locators": [],
                        "confidence": 0.0,
                        "rationale": "self_healing module not installed; returned raw error.",
                    },
                )
        except Exception as e:
            logger.exception("attempt_heal failed: %s", e)
            return ToolResult(success=False, output=f"attempt_heal error: {e}", error=str(e))

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "test_name": {
                        "type": "string",
                        "description": "Fully-qualified test name (e.g. 'tests/test_login.py::test_signup').",
                    },
                    "error": {
                        "type": "string",
                        "description": "Failure message / stack-trace excerpt.",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Optional test run id for correlation.",
                    },
                    "locator": {
                        "type": "string",
                        "description": "The original locator that failed (CSS / XPath / accessibility id).",
                    },
                },
                "required": ["test_name"],
            },
        )


from harness.tools.registry import registry

registry.register(AttemptHealTool(), toolset="healing")

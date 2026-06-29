"""EvalBridge — thin wrapper around Langfuse's native evaluation platform.

Uses the official Langfuse Python SDK datasets + experiments API.
No homegrown eval framework — delegate to the platform.

Usage:
    from harness.eval.bridge import EvalBridge

    bridge = EvalBridge()

    # Create a dataset with golden trajectories
    await bridge.create_dataset("agent-golden", [
        {"input": "deploy to prod", "expected_output": "deployed"},
    ])

    # Run an experiment against it
    result = await bridge.run_experiment(
        dataset_name="agent-golden",
        agent_fn=lambda input: agent.run(input),
        experiment_name="v1.2.0",
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

_INIT_FAILED = object()


class EvalBridge:
    """Thin bridge to Langfuse's native evaluation.

    Fail-open: silently no-ops when langfuse SDK or credentials
    are unavailable.
    """

    def __init__(self) -> None:
        self._client = _get_client()
        self._available = self._client is not None

    @property
    def available(self) -> bool:
        return self._available

    async def create_dataset(
        self,
        name: str,
        items: list[dict[str, Any]],
        description: str = "",
    ) -> bool:
        """Create a dataset in Langfuse with the given items.

        Each item must have ``input`` (required) and optionally
        ``expected_output`` and ``metadata``.
        """
        if not self._available or self._client is None:
            return False
        try:
            ds = self._client.create_dataset(name=name, description=description)
            for item in items:
                self._client.create_dataset_item(
                    dataset_name=name,
                    input=item["input"],
                    expected_output=item.get("expected_output"),
                    metadata=item.get("metadata"),
                )
            logger.info("Created Langfuse dataset '%s' with %d items", name, len(items))
            return True
        except Exception as exc:
            logger.warning("Failed to create Langfuse dataset '%s': %s", name, exc)
            return False

    async def run_experiment(
        self,
        dataset_name: str,
        agent_fn: Callable[[Any], Any],
        experiment_name: str | None = None,
        evaluators: list[Any] | None = None,
    ) -> Any | None:
        """Run an experiment on a Langfuse-hosted dataset.

        Each dataset item is passed to ``agent_fn(item.input)``.
        Results are automatically traced and linked to dataset items.
        """
        if not self._available or self._client is None:
            return None
        if not experiment_name:
            experiment_name = f"eval-{datetime.now(timezone.utc).isoformat()}"

        def _task(*, item: Any, **kwargs: Any) -> Any:
            return agent_fn(item.input) if hasattr(item, "input") else agent_fn(item)

        try:
            dataset = self._client.get_dataset(dataset_name)
            result = dataset.run_experiment(
                name=experiment_name,
                task=_task,
                evaluators=evaluators or [],
            )
            logger.info("Experiment '%s' completed on dataset '%s'", experiment_name, dataset_name)
            return result
        except Exception as exc:
            logger.warning("Experiment '%s' failed: %s", experiment_name, exc)
            return None

    async def run_local_experiment(
        self,
        items: list[dict[str, Any]],
        agent_fn: Callable[[Any], Any],
        experiment_name: str | None = None,
        evaluators: list[Any] | None = None,
    ) -> Any | None:
        """Run an experiment on a local (not Langfuse-hosted) dataset.

        Traces and scores are still sent to Langfuse, but the dataset
        is not stored on Langfuse's side.
        """
        if not self._available or self._client is None:
            return None
        if not experiment_name:
            experiment_name = f"eval-local-{datetime.now(timezone.utc)}"

        def _task(*, item: Any, **kwargs: Any) -> Any:
            if isinstance(item, dict):
                return agent_fn(item.get("input", item))
            return agent_fn(item)

        try:
            result = self._client.run_experiment(
                name=experiment_name,
                data=items,
                task=_task,
                evaluators=evaluators or [],
            )
            logger.info("Local experiment '%s' completed with %d items", experiment_name, len(items))
            return result
        except Exception as exc:
            logger.warning("Local experiment '%s' failed: %s", experiment_name, exc)
            return None


_client_cache: Any | None = None


def _get_client() -> Any | None:
    """Return cached Langfuse client, or None if unavailable."""
    global _client_cache
    if _client_cache is _INIT_FAILED:
        return None
    if _client_cache is not None:
        return _client_cache

    try:
        from langfuse import get_client

        client = get_client()
        _client_cache = client
        return client
    except Exception as exc:
        logger.debug("Langfuse client not available for eval: %s", exc)
        _client_cache = _INIT_FAILED
        return None

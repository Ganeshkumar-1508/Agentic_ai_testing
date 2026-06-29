"""A2A Server — FastAPI router exposing the TestAI orchestrator as
an A2A v1.0 Server.

Routes:

  - `GET  /.well-known/agent.json` — Agent Card discovery
  - `POST /a2a/jsonrpc`           — JSON-RPC 2.0 dispatcher
        methods:
          - `SendMessage`           — submit a job, return a Task
          - `SendStreamingMessage`  — submit + SSE stream
          - `GetTask`               — poll a Task
          - `CancelTask`            — cancel a Task

All other methods return JSON-RPC error -32601 (method not
found). All route methods are async and use the existing
C08 seams (`submit_job_to_orchestrator`, `JobSpecStore.*`,
`EventSourceSink.subscribe`).

Reference: `docs/2026-06-21-c05-design.md`.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from .mapping import (
    artifact_from_output,
    job_record_to_task,
    message_to_job_spec,
    request_to_message,
)
from .stream import a2a_stream_from_session
from .types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    AgentAuthentication,
    JSONRPCError,
    JSONRPCErrorCode,
    JSONRPCRequest,
    JSONRPCResponse,
    Task,
    TaskState,
    TaskStatus,
    job_status_to_a2a_state,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


a2a_router = APIRouter(prefix="/a2a", tags=["a2a"])


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------


AGENT_CARD_PATH = "/.well-known/agent.json"


def _default_a2a_url() -> str:
    """Compute the A2A JSON-RPC URL from the env.

    Order: ``A2A_PUBLIC_URL`` → ``EXTERNAL_URL``/a2a/jsonrpc →
    ``http://localhost:8001/a2a/jsonrpc``. The Agent Card
    advertises the URL clients should use; this is the
    discovery contract.
    """
    explicit = os.environ.get("A2A_PUBLIC_URL")
    if explicit:
        return explicit.rstrip("/")
    base = os.environ.get("EXTERNAL_URL", "http://localhost:8001").rstrip("/")
    return f"{base}/a2a/jsonrpc"


def build_agent_card(
    *,
    url: str | None = None,
    version: str = "1.0.0",
) -> AgentCard:
    """Build the static Agent Card.

    The card is built at request time so the `url` reflects
    the deployment, not a hardcoded string. The `skills`
    list is the test-generation surface TestAI currently
    offers; future skills (healing, coverage gap, etc.)
    are added by extending the list.
    """
    return AgentCard(
        name="TestAI Agent",
        description=(
            "Autonomous test-generation agent harness. Submits a JobSpec, "
            "runs a coordinator, spawns subagents, opens PRs. "
            "Maps TestAI's `paused` state to A2A's `TASK_STATE_INPUT_REQUIRED` "
            "— TestAI is a task-generating agent and never returns a `Message`."
        ),
        url=url or _default_a2a_url(),
        version=version,
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            stateTransitionHistory=False,
        ),
        defaultInputModes=["text", "data", "url"],
        defaultOutputModes=["text", "data"],
        skills=[
            AgentSkill(
                id="generate-tests",
                name="Generate tests",
                description=(
                    "Generate, run, and open a PR for a test suite against a "
                    "given repository."
                ),
                inputModes=["text", "data", "url"],
                outputModes=["text", "data"],
                examples=[
                    "Add Jest tests for the auth module in github.com/acme/api",
                    "Write Playwright e2e for the checkout flow in github.com/acme/web",
                ],
                tags=["testing", "code-generation"],
            ),
            AgentSkill(
                id="review-and-fix",
                name="Review and fix",
                description=(
                    "Diagnose a flaky test or regression, propose a fix, "
                    "and open a PR."
                ),
                inputModes=["text", "url"],
                outputModes=["text", "data"],
                examples=[
                    "The checkout test is flaky in github.com/acme/web; diagnose and fix",
                ],
                tags=["testing", "debugging"],
            ),
            AgentSkill(
                id="kanban-review",
                name="Kanban review",
                description=(
                    "Tier-2 supervised review: post to the review queue, "
                    "await human approval, then commit+PR."
                ),
                inputModes=["text", "data"],
                outputModes=["text", "data"],
                tags=["testing", "review", "tier-2"],
            ),
        ],
        authentication=AgentAuthentication(schemes=["bearer"]),
    )


# The agent card is mounted at the spec-required `/.well-known/agent.json`
# path. FastAPI doesn't allow `/.well-known` as a route prefix easily,
# so we mount it on the root router and also expose a convenience
# mount at `/a2a/.well-known/agent.json` for clients that prepend the
# router prefix from the Agent Card's `url`.
agent_card_router = APIRouter(tags=["a2a"])


@agent_card_router.get(AGENT_CARD_PATH, include_in_schema=False)
async def agent_card_root() -> JSONResponse:
    """A2A Agent Card at the spec-mandated location."""
    return JSONResponse(content=build_agent_card().model_dump(exclude_none=True))


@a2a_router.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card_a2a_prefixed() -> JSONResponse:
    """Convenience mount at ``/a2a/.well-known/agent.json``.

    Some A2A clients naively prepend the router prefix to the
    `.well-known` path; we serve the same card from both
    locations so they always find us.
    """
    return JSONResponse(content=build_agent_card().model_dump(exclude_none=True))


# ---------------------------------------------------------------------------
# Helpers — store / orchestrator / sink access
# ---------------------------------------------------------------------------


def _get_store(request: Request) -> Any:
    """Return the wired `JobSpecStore` from app state or the module."""
    store = getattr(request.app.state, "job_spec_store", None)
    if store is not None:
        return store
    try:
        from harness.jobs.spec import _job_spec_store as _module_store
        return _module_store()
    except Exception as exc:  # pragma: no cover
        logger.debug("/a2a: JobSpecStore not available: %s", exc)
        return None


def _get_orchestrator_factory(request: Request) -> Any:
    """Return a callable that builds an `OrchestratorEngine`."""
    factory = getattr(request.app.state, "orchestrator_engine_factory", None)
    if factory is not None:
        return factory
    try:
        from harness.orchestrator import OrchestratorEngine
        return lambda: OrchestratorEngine.create_default()
    except Exception as exc:  # pragma: no cover
        logger.debug("/a2a: OrchestratorEngine unavailable: %s", exc)
        return None


def _get_sink(request: Request) -> Any:
    """Return the wired `EventSourceSink` (for streaming)."""
    return getattr(request.app.state, "event_source_sink", None)


def _error_response(
    rpc_id: str | int | None,
    code: int,
    message: str,
    data: Any | None = None,
) -> JSONRPCResponse:
    """Build a JSON-RPC error response."""
    return JSONRPCResponse(
        id=rpc_id,
        error=JSONRPCError(code=code, message=message, data=data),
    )


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 dispatcher
# ---------------------------------------------------------------------------


@a2a_router.post("/jsonrpc")
async def jsonrpc_dispatcher(request: Request, body: JSONRPCRequest) -> JSONResponse:
    """Single JSON-RPC 2.0 endpoint for all A2A methods.

    Dispatches on `body.method` to one of `SendMessage`,
    `SendStreamingMessage`, `GetTask`, or `CancelTask`. Unknown
    methods return JSON-RPC -32601. Invalid params return -32602.
    Internal errors return -32603.

    Streaming is handled by a separate endpoint (`/jsonrpc/stream`)
    because `EventSourceResponse` needs the request body, and
    FastAPI's request body parsing is incompatible with the
    SSE response shape when the dispatcher is one route. The
    streaming endpoint re-uses the same validation + dispatch
    table.
    """
    method = body.method
    rpc_id = body.id
    try:
        if method == "SendMessage":
            return await _handle_send_message(request, body, rpc_id)
        if method == "GetTask":
            return await _handle_get_task(request, body, rpc_id)
        if method == "CancelTask":
            return await _handle_cancel_task(request, body, rpc_id)
        if method == "tasks/resubscribe":
            return await _handle_resubscribe(request, body, rpc_id)
        if method == "tasks/pushNotificationConfig/set":
            return await _handle_push_config_set(request, body, rpc_id)
        if method == "tasks/pushNotificationConfig/get":
            return await _handle_push_config_get(request, body, rpc_id)
        if method == "tasks/pushNotificationConfig/list":
            return await _handle_push_config_list(request, body, rpc_id)
        if method == "tasks/pushNotificationConfig/delete":
            return await _handle_push_config_delete(request, body, rpc_id)
        if method == "SendStreamingMessage":
            # The client should use the SSE endpoint for streaming.
            # We return an error here so they get a clean JSON-RPC
            # response, not a 404.
            return JSONResponse(
                content=_error_response(
                    rpc_id,
                    JSONRPCErrorCode.UNSUPPORTED_OPERATION,
                    "SendStreamingMessage requires the SSE endpoint; POST to /a2a/jsonrpc/stream with `Accept: text/event-stream`",
                ).model_dump(exclude_none=True),
                status_code=200,
            )
        # Unknown method
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.METHOD_NOT_FOUND,
                f"Method '{method}' not found",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    except Exception as exc:
        logger.exception("A2A dispatcher error: method=%s", method)
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                f"Internal error: {exc}",
            ).model_dump(exclude_none=True),
            status_code=200,
        )


# ---------------------------------------------------------------------------
# SendMessage — submit a job, return a Task
# ---------------------------------------------------------------------------


async def _handle_send_message(
    request: Request, body: JSONRPCRequest, rpc_id: str | int | None,
) -> JSONResponse:
    """Implement the A2A `SendMessage` method.

    Body: ``{ "params": { "message": { role, messageId, parts: [...] } } }``

    Returns: ``{ "result": { "task": { id, contextId, status, artifacts } } }``

    Side effects: persists a `JobSpecRecord` and dispatches the
    orchestrator. Same seam as `POST /api/jobs`.
    """
    try:
        message = request_to_message(body)
    except ValueError as exc:
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS, str(exc),
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    try:
        spec_dict = message_to_job_spec(message)
    except ValueError as exc:
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS, str(exc),
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    # Carry A2A-side metadata into the spec for traceability.
    spec_dict.setdefault("context", {})["a2a_message_id"] = message.messageId
    if message.contextId:
        spec_dict["context"].setdefault("session_id", message.contextId)

    # Tier / capabilities / source can come from message.metadata.
    if isinstance(message.metadata, dict):
        spec_dict["tier"] = int(message.metadata.get("tier", spec_dict.get("tier", 1)))
        if "capabilities" in message.metadata and isinstance(
            message.metadata["capabilities"], list,
        ):
            spec_dict["capabilities"] = list(message.metadata["capabilities"])
        if "source" in message.metadata:
            spec_dict["source"] = str(message.metadata["source"])

    store = _get_store(request)
    factory = _get_orchestrator_factory(request)
    if store is None:
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                "JobSpecStore not configured; backend not started cleanly",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    from harness.jobs.spec import JobSpec
    from harness.jobs.submitter import submit_job_to_orchestrator

    spec = JobSpec.from_dict(spec_dict)
    try:
        run_id = await submit_job_to_orchestrator(
            spec,
            job_spec_store=store,
            orchestrator_engine_factory=factory,
        )
    except Exception as exc:
        logger.exception("a2a: submit_job_to_orchestrator failed")
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                f"Failed to submit job: {exc}",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    # Build the response Task. We don't reload from the store
    # (we just wrote it; the orchestrator is still spinning up).
    task = Task(
        id=spec.spec_id,
        contextId=spec_dict["context"].get("session_id") or spec.spec_id,
        status=TaskStatus(
            state=TaskState.SUBMITTED,
            message="Job submitted" + (f"; run_id={run_id}" if run_id else ""),
        ),
        artifacts=[],
        metadata={"run_id": run_id or "", "tier": spec.tier, "source": spec.source},
    )
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            result={"task": task.model_dump(exclude_none=True, mode="json")},
        ).model_dump(exclude_none=True),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# GetTask — poll a Task
# ---------------------------------------------------------------------------


async def _handle_get_task(
    request: Request, body: JSONRPCRequest, rpc_id: str | int | None,
) -> JSONResponse:
    """Implement the A2A `GetTask` method.

    Body: ``{ "params": { "id": "<spec_id>" } }``

    Returns: ``{ "result": { "task": { ... } } }``

    Loads the spec from the store; if completed, attaches the
    `JobOutput` artifacts. This mirrors the `/api/jobs/{id}` and
    `/api/jobs/{id}/output` GET endpoints.
    """
    params = body.params or {}
    task_id = params.get("id") or params.get("taskId")
    if not task_id or not isinstance(task_id, str):
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INVALID_PARAMS,
                "params.id is required for GetTask",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    store = _get_store(request)
    if store is None:
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                "JobSpecStore not configured",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    record = await store.get(task_id)
    if record is None:
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.TASK_NOT_FOUND,
                f"Task '{task_id}' not found",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    # If the job produced output, attach the artifacts.
    artifacts: list = []
    try:
        output = await store.get_output(task_id)
        if output is not None:
            artifacts = artifact_from_output(output)
    except Exception as exc:
        logger.debug("a2a.GetTask: get_output failed: %s", exc)

    task = job_record_to_task(record, artifacts=artifacts)
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            result={"task": task.model_dump(exclude_none=True, mode="json")},
        ).model_dump(exclude_none=True),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# CancelTask — cancel a running job
# ---------------------------------------------------------------------------


async def _handle_cancel_task(
    request: Request, body: JSONRPCRequest, rpc_id: str | int | None,
) -> JSONResponse:
    """Implement the A2A `CancelTask` method.

    Body: ``{ "params": { "id": "<spec_id>" } }``

    Returns: ``{ "result": { "task": { ... canceled state ... } } }``

    The cancel races with the orchestrator's run loop. We
    return the post-cancel state of the spec; the client
    polls `GetTask` (or subscribes to the stream) to confirm
    the transition to `CANCELED`.
    """
    params = body.params or {}
    task_id = params.get("id") or params.get("taskId")
    if not task_id or not isinstance(task_id, str):
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INVALID_PARAMS,
                "params.id is required for CancelTask",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    store = _get_store(request)
    if store is None:
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                "JobSpecStore not configured",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    # The C08 cancel/pause watcher only cancels running jobs;
    # terminal jobs (completed, failed, cancelled) return False.
    record = await store.get(task_id)
    if record is None:
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.TASK_NOT_FOUND,
                f"Task '{task_id}' not found",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    current_state = job_status_to_a2a_state(
        getattr(record, "status", "pending") or "pending",
    )
    if current_state in (
        TaskState.COMPLETED, TaskState.FAILED,
        TaskState.CANCELED, TaskState.REJECTED,
    ):
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.TASK_NOT_CANCELABLE,
                f"Task '{task_id}' is in terminal state {current_state}; cannot cancel",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    ok = await store.cancel(task_id)
    if not ok:
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.TASK_NOT_CANCELABLE,
                f"Task '{task_id}' is not cancellable (already terminal?)",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    # Re-read the record so the response shows the new state.
    updated = await store.get(task_id) or record
    task = job_record_to_task(updated)
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            result={"task": task.model_dump(exclude_none=True, mode="json")},
        ).model_dump(exclude_none=True),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# tasks/pushNotificationConfig/* — A2A spec methods (C05-b polish)
# ---------------------------------------------------------------------------


# In-memory push-notification config store. The A2A spec
# defines 4 methods: set, get, list, delete. C05-b ships the
# in-memory backend; a Postgres-backed store is a follow-up.
_push_configs: dict[str, list[dict[str, Any]]] = {}


def _push_configs_for_task(task_id: str) -> list[dict[str, Any]]:
    return list(_push_configs.get(task_id, []))


def _set_push_config(task_id: str, config: dict[str, Any]) -> None:
    configs = _push_configs.setdefault(task_id, [])
    url = config.get("url", "")
    existing = next(
        (c for c in configs if c.get("url") == url),
        None,
    )
    if existing is not None:
        existing.update(config)
    else:
        configs.append(dict(config))


def _get_push_config(task_id: str, config_id: str | None = None) -> dict[str, Any] | None:
    configs = _push_configs.get(task_id, [])
    if not configs:
        return None
    if config_id is None:
        return configs[0]
    for c in configs:
        if c.get("config_id") == config_id:
            return c
    return None


def _delete_push_config(task_id: str, config_id: str | None = None) -> bool:
    configs = _push_configs.get(task_id, [])
    if not configs:
        return False
    if config_id is None:
        _push_configs.pop(task_id, None)
        return True
    for i, c in enumerate(configs):
        if c.get("config_id") == config_id:
            configs.pop(i)
            return True
    return False


async def _handle_push_config_set(
    request: Request, body: JSONRPCRequest, rpc_id: str | int | None,
) -> JSONResponse:
    params = body.params or {}
    task_id = params.get("id") or params.get("taskId")
    if not task_id or not isinstance(task_id, str):
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS,
                "params.id is required for tasks/pushNotificationConfig/set",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    url = params.get("url")
    if not url or not isinstance(url, str):
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS,
                "params.url is required for tasks/pushNotificationConfig/set",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    config_id = params.get("config_id") or f"pn-{uuid.uuid4().hex[:8]}"
    config = {
        "config_id": config_id,
        "task_id": task_id,
        "url": url,
        "events": list(params.get("events") or ["status", "artifact"]),
        "auth_token": params.get("auth_token"),
        "created_at": __import__("datetime").datetime.now(
            tz=__import__("datetime").timezone.utc,
        ).isoformat(),
    }
    _set_push_config(task_id, config)
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            result={"config": config},
        ).model_dump(exclude_none=True),
        status_code=200,
    )


async def _handle_push_config_get(
    request: Request, body: JSONRPCRequest, rpc_id: str | int | None,
) -> JSONResponse:
    params = body.params or {}
    task_id = params.get("id") or params.get("taskId")
    if not task_id or not isinstance(task_id, str):
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS,
                "params.id is required for tasks/pushNotificationConfig/get",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    config_id = params.get("config_id")
    config = _get_push_config(task_id, config_id)
    if config is None:
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.TASK_NOT_FOUND,
                f"No push config for task '{task_id}'",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            result={"config": config},
        ).model_dump(exclude_none=True),
        status_code=200,
    )


async def _handle_push_config_list(
    request: Request, body: JSONRPCRequest, rpc_id: str | int | None,
) -> JSONResponse:
    params = body.params or {}
    task_id = params.get("id") or params.get("taskId")
    if not task_id or not isinstance(task_id, str):
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS,
                "params.id is required for tasks/pushNotificationConfig/list",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            result={"configs": _push_configs_for_task(task_id)},
        ).model_dump(exclude_none=True),
        status_code=200,
    )


async def _handle_push_config_delete(
    request: Request, body: JSONRPCRequest, rpc_id: str | int | None,
) -> JSONResponse:
    params = body.params or {}
    task_id = params.get("id") or params.get("taskId")
    if not task_id or not isinstance(task_id, str):
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS,
                "params.id is required for tasks/pushNotificationConfig/delete",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    config_id = params.get("config_id")
    deleted = _delete_push_config(task_id, config_id)
    if not deleted:
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.TASK_NOT_FOUND,
                f"No push config for task '{task_id}'",
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            result={"deleted": True, "config_id": config_id},
        ).model_dump(exclude_none=True),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# tasks/resubscribe — A2A spec method (C05-b polish)
# ---------------------------------------------------------------------------


async def _handle_resubscribe(
    request: Request, body: JSONRPCRequest, rpc_id: str | int | None,
) -> JSONResponse:
    """Implement the A2A ``tasks/resubscribe`` method.

    Per the A2A v1.0 spec, ``tasks/resubscribe`` is the recovery
    path for clients that lost the SSE stream mid-task. The
    spec allows the server to:

      1. Return a fresh SSE stream (preferred for in-flight tasks)
      2. Return a final ``Task`` object if the task is already
         terminal (the client doesn't need a stream, just the
         final state)
      3. Return an error if the task is unknown

    We implement #2 + #3 here and defer #1 to the SSE endpoint
    (``POST /a2a/jsonrpc/stream`` with method
    ``SendStreamingMessage`` against the same task id). The
    two-path model keeps the JSON-RPC surface synchronous and
    the SSE surface streaming.
    """
    params = body.params or {}
    task_id = params.get("id") or params.get("taskId")
    if not task_id or not isinstance(task_id, str):
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS,
                "params.id is required for tasks/resubscribe",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    store = _get_store(request)
    if store is None:
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INTERNAL_ERROR,
                "JobSpecStore not configured",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    record = await store.get(task_id)
    if record is None:
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.TASK_NOT_FOUND,
                f"Task '{task_id}' not found",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    artifacts: list = []
    try:
        output = await store.get_output(task_id)
        if output is not None:
            artifacts = artifact_from_output(output)
    except Exception:
        pass

    task = job_record_to_task(record, artifacts=artifacts)
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            result={
                "task": task.model_dump(exclude_none=True, mode="json"),
                "stream_endpoint": "/a2a/jsonrpc/stream",
                "hint": (
                    "Task is in flight; resubscribe via the SSE endpoint "
                    "with SendStreamingMessage to receive ongoing events."
                    if (record.status or "") in ("running", "submitted", "queued", "paused")
                    else "Task is terminal; the Task object is the final state."
                ),
            },
        ).model_dump(exclude_none=True),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# SendStreamingMessage — submit + SSE stream (separate endpoint)
# ---------------------------------------------------------------------------


@a2a_router.post("/jsonrpc/stream")
async def jsonrpc_stream(request: Request, body: JSONRPCRequest):
    """SSE endpoint for `SendStreamingMessage`.

    Accepts the same JSON-RPC body as `/jsonrpc`, but
    returns an `EventSourceResponse` (text/event-stream) of
    A2A `TaskStatusUpdateEvent` and `TaskArtifactUpdateEvent`
    frames.

    The endpoint:

      1. Parses the JSON-RPC body and the embedded A2A Message.
      2. Submits a JobSpec via `submit_job_to_orchestrator` —
         same seam as `SendMessage`.
      3. Subscribes to `EventSourceSink` for the spec's
         session_id.
      4. Streams the events until the job reaches a terminal
         state, the client disconnects, or the keepalive
         loop times out.
    """
    method = body.method
    rpc_id = body.id
    if method != "SendStreamingMessage":
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.METHOD_NOT_FOUND,
                f"Streaming endpoint only accepts SendStreamingMessage; got '{method}'",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    # Validate + convert the message → spec.
    try:
        message = request_to_message(body)
    except ValueError as exc:
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS, str(exc),
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    try:
        spec_dict = message_to_job_spec(message)
    except ValueError as exc:
        return JSONResponse(
            content=_error_response(
                rpc_id, JSONRPCErrorCode.INVALID_PARAMS, str(exc),
            ).model_dump(exclude_none=True),
            status_code=200,
        )
    spec_dict.setdefault("context", {})["a2a_message_id"] = message.messageId
    if message.contextId:
        spec_dict["context"].setdefault("session_id", message.contextId)
    if isinstance(message.metadata, dict):
        spec_dict["tier"] = int(message.metadata.get("tier", spec_dict.get("tier", 1)))
        if "capabilities" in message.metadata and isinstance(
            message.metadata["capabilities"], list,
        ):
            spec_dict["capabilities"] = list(message.metadata["capabilities"])
        if "source" in message.metadata:
            spec_dict["source"] = str(message.metadata["source"])

    store = _get_store(request)
    factory = _get_orchestrator_factory(request)
    if store is None:
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                "JobSpecStore not configured",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    from harness.jobs.spec import JobSpec
    from harness.jobs.submitter import submit_job_to_orchestrator

    spec = JobSpec.from_dict(spec_dict)
    try:
        run_id = await submit_job_to_orchestrator(
            spec,
            job_spec_store=store,
            orchestrator_engine_factory=factory,
        )
    except Exception as exc:
        logger.exception("a2a stream: submit_job_to_orchestrator failed")
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                f"Failed to submit job: {exc}",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    # Determine the session_id for the SSE subscription. The
    # spec's `context.session_id` is the A2A `contextId` (or
    # the spec_id fallback). The orchestrator may emit events
    # to a different session_id (the run's own UUID); the
    # bridge should subscribe to both. For C05 we subscribe
    # to the spec's session_id; the run is expected to share
    # the same session_id (per C08 Q9).
    session_id = str(spec_dict["context"].get("session_id") or spec.spec_id)

    sink = _get_sink(request)
    if sink is None:
        # No sink wired — we can't stream. Return a JSON-RPC
        # error so the client knows to fall back to polling.
        return JSONResponse(
            content=_error_response(
                rpc_id,
                JSONRPCErrorCode.INTERNAL_ERROR,
                "EventSourceSink not configured; cannot stream",
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    task_id = spec.spec_id
    context_id = str(spec_dict["context"].get("session_id") or task_id)

    # Emit an initial status-update so the client sees the
    # task is submitted before the orchestrator's first
    # event lands.
    initial_frames: list[dict[str, str]] = []
    from .stream import _format_status_event
    initial_frames.append(_format_status_event(
        rpc_id=rpc_id, task_id=task_id, context_id=context_id,
        state=TaskState.SUBMITTED,
        message=(
            f"Job submitted (run_id={run_id})" if run_id else "Job submitted"
        ),
    ))

    async def pre_populated():
        for f in initial_frames:
            yield f
        async for f in a2a_stream_from_session(
            sink=sink,
            session_id=session_id,
            task_id=task_id,
            context_id=context_id,
            rpc_id=rpc_id,
            is_disconnected=request.is_disconnected,
        ):
            yield f

    return EventSourceResponse(pre_populated())


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "a2a_router",
    "agent_card_router",
    "build_agent_card",
    "AGENT_CARD_PATH",
]

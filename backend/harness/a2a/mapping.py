"""Mapping between A2A Messages and TestAI JobSpec / JobOutput.

Pure functions. No I/O. The server router calls these to:

  - Convert an incoming A2A `Message` into a `JobSpec` for
    `submit_job_to_orchestrator` (C08 seam).
  - Convert a stored `JobSpecRecord` into an A2A `Task` for the
    `GetTask` response and the initial `SendMessage` response.
  - Convert a final `JobOutput` into 1-3 A2A `Artifact` objects
    for the `completed` Task state.

Reference: `docs/2026-06-21-c05-design.md` §part-jobspec-mapping
and §artifact-joboutput-mapping.
"""
from __future__ import annotations

import uuid
from typing import Any

from .types import (
    Artifact,
    DataPart,
    FilePart,
    Message,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
    job_status_to_a2a_state,
)


# ---------------------------------------------------------------------------
# A2A Message → JobSpec
# ---------------------------------------------------------------------------


def message_to_job_spec(
    message: Message,
    *,
    tier: int = 1,
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Convert an A2A `Message` into a `JobSpec` dict (the C08 shape).

    Mapping rules (see design doc §part-jobspec-mapping):

    - All `text` parts are concatenated with ``"\\n\\n"`` separators
      and become the `prompt`.
    - The first `url` part becomes `repo_url`.
    - All `data` parts are merged into `context`. If a data part
      has a ``metadata.title``, the part is stored under
      ``context[title]``; otherwise the part is spread flat.
    - `raw` (file bytes) parts raise `ValueError` — C05 doesn't
      support file ingestion.

    The returned dict is **plain JSON** so the caller can pass
    it directly to `JobSpec.from_dict()` (C08) or to the
    `JobSpecRequest` Pydantic model (`api/routers/jobs.py`).

    `tier` and `capabilities` are passed through; the A2A spec
    doesn't carry these so the server router (or a future
    `Message.metadata` extension) decides the values. Default
    tier=1 (autonomous) with the standard test-runner
    capabilities is the safe default.
    """
    prompt_parts: list[str] = []
    repo_url: str = ""
    context: dict[str, Any] = {}
    file_parts_seen = 0

    for part in message.parts:
        if isinstance(part, TextPart):
            prompt_parts.append(part.text)
        elif isinstance(part, FilePart):
            file_parts_seen += 1
            if part.raw is not None:
                # C05 doesn't support inline file bytes. The spec
                # says "Implementers can decide to either raise an
                # exception or provide a default"; we raise with
                # a clear message so the client knows.
                raise ValueError(
                    "A2A FilePart with inline `raw` bytes is not supported in C05. "
                    "Use a `url` part or upload via the REST surface."
                )
            # url-bearing FilePart is treated as the repo URL.
            if part.url and not repo_url:
                repo_url = part.url
        elif isinstance(part, DataPart):
            # Data parts become context. If a metadata.title is
            # present we nest the part under that key (so a client
            # can carry "test_config" or "approval" explicitly);
            # otherwise we spread the part flat.
            title = None
            if part.metadata and isinstance(part.metadata, dict):
                title = part.metadata.get("title")
            if title:
                context[title] = part.data
            else:
                context.update(part.data)
        else:  # pragma: no cover — discriminated union
            raise ValueError(f"unknown A2A Part type: {type(part).__name__}")

    prompt = "\n\n".join(p.strip() for p in prompt_parts if p.strip())

    # Defaults for top-level fields. Overridden by message.metadata below.
    a2a_source = "a2a"

    # Pull A2A-side metadata into the spec. The `contextId`
    # becomes the `session_id` so the dashboard groups the job
    # with the chat session that originated the A2A call. The
    # `tier` / `capabilities` / `source` keys override the
    # defaults (which the chat or the orchestrator would
    # otherwise set). Unknown keys are passed through into
    # the spec's `context` so future A2A clients can carry
    # extra metadata without a schema migration.
    if message.contextId:
        context.setdefault("session_id", message.contextId)
    if message.metadata and isinstance(message.metadata, dict):
        # tier / capabilities / source override the spec-level
        # fields. We don't blindly spread — these are the only
        # top-level keys an A2A client can meaningfully set.
        for key in ("tier", "capabilities", "approval", "source"):
            if key in message.metadata:
                context.setdefault(key, message.metadata[key])
        if "tier" in message.metadata:
            tier = int(message.metadata["tier"])
        if "capabilities" in message.metadata and isinstance(
            message.metadata["capabilities"], list,
        ):
            capabilities = list(message.metadata["capabilities"])
        if "source" in message.metadata:
            a2a_source = str(message.metadata["source"])

    # The returned dict matches `JobSpec.from_dict`'s input
    # shape. `run_id` is left empty — the orchestrator overwrites.
    spec_dict: dict[str, Any] = {
        "spec_id": str(uuid.uuid4()),
        "run_id": "",
        "source": a2a_source,
        "prompt": prompt,
        "repo_url": repo_url,
        "branch": "main",
        "sha": "",
        "tier": int(tier),
        "capabilities": list(capabilities) if capabilities is not None else [
            "read_code",
            "write_test_files",
            "edit_existing_tests",
            "run_tests",
            "open_pr",
            "comment_on_pr",
        ],
        "approval": {
            "mode": "review_queue",
            "destination": "github_pr",
        },
        "context": context,
    }
    if file_parts_seen:
        spec_dict["context"]["_a2a_file_parts_seen"] = file_parts_seen
    return spec_dict


# ---------------------------------------------------------------------------
# JobSpecRecord → A2A Task
# ---------------------------------------------------------------------------


def _to_a2a_status(record: Any) -> TaskStatus:
    """Build a `TaskStatus` from a `JobSpecRecord` (or dict)."""
    status_str = getattr(record, "status", None) or (
        record.get("status") if isinstance(record, dict) else None
    ) or "pending"
    state = job_status_to_a2a_state(status_str)
    message_text: str | None = None
    error = getattr(record, "error", None) or (
        record.get("error") if isinstance(record, dict) else None
    )
    if error and state in (TaskState.FAILED, TaskState.CANCELED):
        message_text = str(error)
    timestamp: str | None = None
    completed_at = getattr(record, "completed_at", None) or (
        record.get("completed_at") if isinstance(record, dict) else None
    )
    if completed_at is not None and hasattr(completed_at, "isoformat"):
        timestamp = completed_at.isoformat()
    return TaskStatus(state=state, message=message_text, timestamp=timestamp)


def _record_get(record: Any, key: str, default: Any = None) -> Any:
    """Read a field from a `JobSpecRecord` dataclass or a plain dict.

    The C08 `JobSpecStore` returns dataclass records in
    production; tests sometimes pass plain dicts. This helper
    makes `job_record_to_task` work with either shape.
    """
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def job_record_to_task(
    record: Any,
    *,
    artifacts: list[Artifact] | None = None,
) -> Task:
    """Build an A2A `Task` from a stored `JobSpecRecord` (or dict).

    `record` is the C08 `JobSpecRecord` from the store, or a
    plain dict with the same shape. The `id` is the `spec_id`
    (the durable handle), and the `contextId` is the
    `session_id` from the spec's `context`.
    """
    spec_id = str(_record_get(record, "spec_id", "") or "")
    context_obj = _record_get(record, "context", {}) or {}
    if hasattr(context_obj, "model_dump"):
        ctx = context_obj.model_dump()
    elif isinstance(context_obj, dict):
        ctx = dict(context_obj)
    else:
        ctx = {}
    context_id = str(ctx.get("session_id") or spec_id)

    run_id = str(_record_get(record, "run_id", "") or "")
    source = str(_record_get(record, "source", "") or "")
    tier_raw = _record_get(record, "tier", 1)
    try:
        tier_val: int = int(tier_raw) if tier_raw is not None else 1
    except (TypeError, ValueError):
        tier_val = 1

    return Task(
        id=spec_id,
        contextId=context_id,
        status=_to_a2a_status(record),
        artifacts=list(artifacts or []),
        history=None,  # C05 doesn't keep a history; SSE is the history
        metadata={
            "run_id": run_id,
            "source": source,
            "tier": tier_val,
        },
    )


# ---------------------------------------------------------------------------
# JobOutput → Artifacts
# ---------------------------------------------------------------------------


def artifact_from_output(output: Any) -> list[Artifact]:
    """Build 1-3 A2A `Artifact` objects from a `JobOutput`.

    Mapping rules (see design doc §artifact-joboutput-mapping):

    1. **Test files artifact** — `output.artifacts` filtered to
       file-like entries (have a `path` key) becomes one
       Artifact. Name: ``"test_files"``. Parts: a `text` part
       with the path list (one per line) and a `data` part
       with ``{count, paths}``.

    2. **PR artifact** — if `output.pr_url` is set, one
       Artifact with ``name="pull_request"`` and a `data` part
       carrying ``{url, branch, ...}``.

    3. **Summary artifact** — if `output.summary` is set, one
       Artifact with ``name="summary"`` and a `text` part.

    Returns an empty list if there's nothing to surface (e.g.
    the job was cancelled or failed before producing output).
    """
    artifacts: list[Artifact] = []
    if output is None:
        return artifacts

    # JobOutput is a dataclass; also accept plain dicts.
    def _get(key: str, default: Any = None) -> Any:
        if isinstance(output, dict):
            return output.get(key, default)
        return getattr(output, key, default)

    summary = _get("summary", "") or ""
    pr_url = _get("pr_url", None)
    raw_artifacts = _get("artifacts", []) or []
    spec_id = _get("spec_id", "unknown")

    # 1. test files artifact
    test_paths: list[str] = []
    other_artifacts: list[dict[str, Any]] = []
    for art in raw_artifacts:
        if isinstance(art, dict):
            path = art.get("path") or art.get("filename")
            if path:
                test_paths.append(str(path))
                continue
        other_artifacts.append(art if isinstance(art, dict) else {"value": str(art)})
    if test_paths:
        artifacts.append(
            Artifact(
                artifactId=f"art-tests-{spec_id}",
                name="test_files",
                description=(
                    f"{len(test_paths)} test file(s) generated by the agent"
                ),
                parts=[
                    TextPart(text="\n".join(test_paths)),
                    DataPart(
                        data={"count": len(test_paths), "paths": test_paths},
                        metadata={"title": "test_files"},
                    ),
                ],
            )
        )
    if other_artifacts:
        artifacts.append(
            Artifact(
                artifactId=f"art-other-{spec_id}",
                name="other_artifacts",
                description="Other artifacts produced by the agent",
                parts=[DataPart(
                    data={"artifacts": other_artifacts},
                    metadata={"title": "other_artifacts"},
                )],
            )
        )

    # 2. PR artifact
    if pr_url:
        artifacts.append(
            Artifact(
                artifactId=f"art-pr-{spec_id}",
                name="pull_request",
                description="Pull request opened by the agent",
                parts=[DataPart(
                    data={
                        "url": pr_url,
                        "branch": _get("branch", ""),
                        "title": summary[:120] if summary else "",
                    },
                    metadata={"title": "pull_request"},
                )],
            )
        )

    # 3. Summary artifact
    if summary:
        artifacts.append(
            Artifact(
                artifactId=f"art-summary-{spec_id}",
                name="summary",
                description="Final summary of the agent's work",
                parts=[TextPart(text=summary)],
            )
        )

    return artifacts


# ---------------------------------------------------------------------------
# JSON-RPC request → A2A Message
# ---------------------------------------------------------------------------


def request_to_message(request: Any) -> Message:
    """Extract an A2A `Message` from a JSON-RPC `params.message`.

    A2A v1.0 puts the message under ``params.message`` for
    `SendMessage` and `SendStreamingMessage`. The server router
    calls this and forwards the result to `message_to_job_spec`.

    Raises `ValueError` (caught by the router and turned into a
    JSON-RPC -32602 error) if the params are missing the
    required `message` field.
    """
    if isinstance(request, dict):
        params = request.get("params") or {}
    else:
        # pydantic JSONRPCRequest
        params = request.params or {}
    msg_payload = params.get("message")
    if not isinstance(msg_payload, dict):
        raise ValueError("params.message is required for SendMessage")
    return Message.model_validate(msg_payload)


__all__ = [
    "artifact_from_output",
    "job_record_to_task",
    "message_to_job_spec",
    "request_to_message",
]

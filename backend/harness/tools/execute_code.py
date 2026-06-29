"""Execute-code tool — sandboxed Python/Node code execution.

The agent uses this when it needs to evaluate a small expression
or run a snippet (e.g. compute a hash, parse a JSON file, verify
a hypothesis). The agent SHOULD use `bash` for general shell work;
this tool is a structured entry point specifically for code.

Two backends:
  - For `bash` and trivial expressions, route through the existing
    `bash` tool (it's already sandboxed by SandboxManager).
  - For longer-running Python, optionally use the `python` REPL with
    RestrictedPython guards. For now, we route everything through
    `bash` to keep a single execution seam.

Module-level deps are injected at app startup via
`set_backend_factory`. If unset, the tool returns a clear
"not available" result and the agent falls back to `bash`.
"""
from __future__ import annotations

import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


_deps_ref: dict[str, Any] = {}


def set_backend_factory(factory: Any) -> None:
    _deps_ref["backend_factory"] = factory


def _backend_factory() -> Any:
    return _deps_ref.get("backend_factory")


_LANGUAGE_HELPERS: dict[str, str] = {
    "python": "python3 -c",
    "python3": "python3 -c",
    "py": "python3 -c",
    "javascript": "node -e",
    "node": "node -e",
    "js": "node -e",
    "typescript": "npx -y ts-node -e",
    "ts": "npx -y ts-node -e",
    "bash": "bash -c",
    "sh": "sh -c",
    "shell": "sh -c",
    "ruby": "ruby -e",
    "rb": "ruby -e",
    "go": "go run /tmp/_snippet.go",  # go doesn't have -e; write to file
}


def _wrap_for_runtime(language: str, code: str) -> tuple[str, str]:
    """Return (shell_command, warning). For Go, we write to a temp file."""
    helper = _LANGUAGE_HELPERS.get(language.lower())
    if not helper:
        return "", f"Unsupported language: {language}. Use one of: {sorted(_LANGUAGE_HELPERS)}"
    if language.lower() in ("go",):
        # Write to /tmp inside the container, then run.
        escaped = code.replace("'", "'\\''")
        cmd = (
            f"mkdir -p /tmp/_ex && cat > /tmp/_ex/main.go <<'__GO_EOF__'\n{code}\n__GO_EOF__\n"
            f"go run /tmp/_ex/main.go"
        )
        return cmd, ""
    escaped = code.replace("'", "'\\''")
    return f"{helper} '{escaped}'", ""


class ExecuteCodeTool(BaseTool):
    name = "execute_code"
    default_level = "ask"
    description = (
        "Execute a short code snippet in a sandboxed container. "
        "Pass `language` (python, javascript, typescript, bash, ruby, "
        "go) and `code`. Returns stdout, stderr, and exit code. For "
        "shell work prefer the `bash` tool; this tool is for evaluating "
        "expressions, parsing data, or running small scripts."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": sorted(set(_LANGUAGE_HELPERS)),
                        "default": "python",
                    },
                    "code": {
                        "type": "string",
                        "description": "Code to execute",
                    },
                    "timeout": {"type": "integer", "default": 30, "minimum": 1, "maximum": 600},
                },
                "required": ["code"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        factory = _backend_factory()
        code = kwargs.get("code")
        if not code or not isinstance(code, str):
            return ToolResult(success=False, output="`code` is required", error="missing_arg")
        if len(code) > 200_000:
            return ToolResult(
                success=False,
                output=f"Code is {len(code)} chars; max 200,000. For long scripts, use `write` + `bash`.",
                error="too_large",
            )
        language = (kwargs.get("language") or "python").lower()
        cmd, warn = _wrap_for_runtime(language, code)
        if not cmd:
            return ToolResult(success=False, output=warn, error="unsupported_language")
        try:
            timeout = max(1, min(600, int(kwargs.get("timeout", 30) or 30)))
        except (TypeError, ValueError):
            timeout = 30
        session_id = kwargs.get("session_id") or "default"
        try:
            if factory is not None:
                backend = factory(session_id, backend_type="docker")
                proc = await backend.run(cmd, timeout=timeout)
            else:
                return ToolResult(
                    success=False,
                    output="Backend not configured. Use the `bash` tool which runs locally.",
                    error="not_initialised",
                )
        except Exception as exc:
            logger.warning("execute_code run failed: %s", exc)
            return ToolResult(
                success=False, output=f"Sandbox exec failed: {exc}",
                error="sandbox_error",
            )
        ok = proc.returncode == 0
        body: list[str] = []
        if warn:
            body.append(f"> {warn}")
        if proc.stdout:
            body.append(f"### stdout\n```\n{proc.stdout.rstrip()}\n```")
        if proc.stderr:
            body.append(f"### stderr\n```\n{proc.stderr.rstrip()}\n```")
        body.append(f"**exit code: {proc.returncode}**")
        return ToolResult(
            success=ok,
            output="\n\n".join(body),
            data={
                "language": language, "stdout": proc.stdout,
                "stderr": proc.stderr, "exit_code": proc.returncode,
            },
        )


registry.register(ExecuteCodeTool(), toolset="read")

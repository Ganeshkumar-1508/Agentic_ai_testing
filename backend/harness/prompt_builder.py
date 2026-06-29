from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import OrderedDict

from harness.tools.toolsets import MODES, prompt_for_mode, system_prompts_for_mode
from harness.tools.skill_tools import _scan_skills
from harness.tools.memory_tool import get_memory_snapshot


def get_reflection_snapshot() -> str:
    """Return the most-recent reflexion entries for system-prompt injection.
    Empty string if none saved yet (no error)."""
    try:
        from harness.agent.reflexion_memory import ReflexionMemory
        return ReflexionMemory().snapshot()
    except Exception:
        return ""
from harness.prompts import load_prompt

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_SKILLS_CACHE_FILE = Path.home() / ".testai" / ".skills_cache.json"
_SKILLS_CACHE_TTL = 300  # 5 minutes
_CONTEXT_FILE_MAX_CHARS = 20_000

# Prompts live in .testai/prompts/ — loaded from disk, never embedded in code
_PROMPTS_ROOT = (Path(__file__).resolve().parent.parent.parent / ".testai" / "prompts")
if not _PROMPTS_ROOT.exists():
    _PROMPTS_ROOT = Path("/app/.testai/prompts")  # Docker fallback


def load_prompt_file(path: Path) -> str:
    """Read a prompt file (any extension: .md, .txt). Returns empty string on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return ""


def load_system_prompt(name: str) -> str:
    """Load a system prompt by name from system-prompts/ (.md files)."""
    base = _PROMPTS_ROOT / "system-prompts"
    for path in [base / name, base / f"system-prompt-{name}.md"]:
        content = load_prompt_file(path)
        if content:
            return content
    return ""


def load_agent_prompt(name: str) -> str:
    """Load an agent prompt from agents/ (.txt ECC format or .md)."""
    base = _PROMPTS_ROOT / "agents"
    for path in [base / name, base / f"{name}.txt", base / f"{name}.md"]:
        content = load_prompt_file(path)
        if content:
            return content
    return ""


def render_prompt(body: str, vars: dict) -> str:
    """Substitute ``{{key}}`` placeholders in body with values from vars.

    Simple ``str.replace``; no Jinja, no template engine. The body is
    a prompt template; ``vars`` maps placeholder names to their
    string values. Unknown placeholders are left untouched.

    Used by the orchestrator to render the coordinator role body with
    the per-run spec vars (capability list, tier-specific instructions,
    etc.). See ``.testai/prompts/agents/coordinator.txt`` for the
    canonical template.
    """
    if not vars:
        return body
    for key, value in vars.items():
        body = body.replace("{{" + key + "}}", "" if value is None else str(value))
    return body


# ---------------------------------------------------------------------------
# Phase-8 P1 #8: clean up any pre-existing 0-byte cache file on import.
# Phase 2 found ``~/.testai/.skills_cache.json`` sitting on disk as an
# empty file \u2014 a half-finished write.  We delete it at import time and
# log a warning so a future regression is visible in the logs.  The
# actual writer (_save_skills_cache below) also uses an atomic
# temp-file + os.replace() to prevent the same failure mode.
# ---------------------------------------------------------------------------
try:
    if _SKILLS_CACHE_FILE.exists() and _SKILLS_CACHE_FILE.stat().st_size == 0:
        import logging as _plog
        _plog.getLogger(__name__).warning(
            "Removing stale 0-byte skills cache at %s", _SKILLS_CACHE_FILE
        )
        _SKILLS_CACHE_FILE.unlink()
except OSError as _cache_cleanup_exc:  # pragma: no cover — defensive
    import logging as _plog
    _plog.getLogger(__name__).debug(
        "Could not pre-clean skills cache: %s", _cache_cleanup_exc
    )


def _build_prompt(
    identity: str,
    system_time: str,
    environment_hints: str,
    mode_block: str = "",
    project_context: str = "",
    memory: str = "",
    extra_context: str = "",
    toolsets: list[str] | None = None,
) -> str:
    """Assemble system prompt with tool-gated loading (Hermes pattern).
    Prompts are loaded based on what tools the agent has.
    """
    tool_set = set(toolsets or [])
    prompts: list[str] = [identity]

    # Tool-gated behavioral guidance (Hermes pattern — right after identity,
    # before anything else, so the agent sees it even when context is tight)
    if any(t.startswith("kanban_") for t in tool_set):
        prompts.append(
            "# Kanban task tracking\n\n"
            "You have kanban tools available for tracking multi-step work.\n\n"
            "## Lifecycle\n"
            "1. **Orient** — `kanban_show()` to read your current task\n"
            "2. **Work** — use your tools (bash, read, write, delegate, etc.)\n"
            "3. **Heartbeat** — `kanban_heartbeat(note=...)` every 60s during long ops\n"
            "4. **Log** — `kanban_comment(task_id, body=...)` to record findings\n"
            "5. **Complete** — `kanban_complete(task_id, summary=...)` when done\n"
            "6. **Block** — `kanban_block(task_id, reason=...)` if stuck\n\n"
            "Kanban is the user's only window into your progress. Keep it updated."
        )

    # Always-loaded prompts — keep lean so the agent has room to think.
    # Everything else is loaded on-demand via skill_view.
    always = [
        "doing-tasks-software-engineering-focus",
        "doing-tasks-ambitious-tasks",
        "doing-tasks-no-compatibility-hacks",
        "doing-tasks-no-unnecessary-error-handling",
        "doing-tasks-security",
        "executing-actions-with-care",
        "action-safety-and-truthful-reporting",
        "autonomous-loop-check",
        "tool-usage-subagent-guidance",
        "subagent-delegation-examples",
        "coordinator-mode-orchestration",
        "coordinator-worker-instructions",
        "communication-style",
    ]
    for pf in always:
        content = load_system_prompt(f"system-prompt-{pf}.md")
        if content:
            prompts.append(content)

    # Tool-gated prompts (Hermes pattern — only when relevant tools are available)
    if "memory" in tool_set:
        c = load_system_prompt("system-prompt-agent-memory-instructions.md")
        if c:
            prompts.append(c)

    if "delegate_task" in tool_set:
        c = load_system_prompt("system-prompt-agent-summary-generation.md")
        if c:
            prompts.append(c)

    # Web research guidance (single source, not duplicated)
    if "web_search" in tool_set or "web_fetch" in tool_set:
        c = load_system_prompt("system-prompt-web-research.md")
        if c:
            prompts.append(c)
        else:
            prompts.append(
                "# Web research\n"
                "Use web_search and web_fetch for current information, docs, and APIs. "
                "Cite sources. Prefer official documentation when available."
            )

    # Tool categories generated from registry
    from harness.tools.toolsets import TOOLSETS
    all_tool_names = set()
    for ts_name, ts_def in TOOLSETS.items():
        all_tool_names.update(ts_def.get("tools", []))
    tool_lines = "\n".join(f"- `{t}`" for t in sorted(all_tool_names)[:60])
    prompts.append(f"## Available Tools\n\n{tool_lines}\n\n_(Full list: use 'tools' for more)_")

    if mode_block:
        prompts.append(mode_block)
    system = f"## System\n\nTime: {system_time}\n{environment_hints}"
    prompts.append(system)
    if project_context:
        prompts.append(f"## Project Context\n\n{project_context}")
    if memory:
        prompts.append(
            f"## Persistent Memory\n\n{memory}\n\n"
            "Memory is injected at session start and does not change mid-session. "
            "Keep entries compact and focused on facts that will still matter later."
        )
    prompts.append(
        "## Creating Skills\n\n"
        "After completing a complex task (5+ tool calls), discovering a non-trivial "
        "workflow, or being corrected by the user, use `skill_manage action=create "
        "name=<name> content=<full SKILL.md>` to preserve what you learned. "
        "Keep skills focused, reusable, and under 200 lines."
    )
    if extra_context:
        prompts.append(f"## Additional Context\n\n{extra_context}")
    return "\n\n---\n\n".join(prompts)


def _build_subagent_prompt(
    goal: str,
    system_time: str,
    allowed_tools: str = "",
    context: str = "",
    extra_instructions: str = "",
) -> str:
    from harness.prompt_builder import load_system_prompt, load_agent_prompt
    # Load reference prompt + add our instructions on top
    base = load_system_prompt("worker-instructions")
    if not base:
        base = load_agent_prompt("planner") or ""
    extra = (
        "## Instructions\n"
        "- Use your tools to complete the task — do not describe what you would do\n"
        "- If you hit an error, diagnose and retry with a different approach\n"
        "- Report: what you did, what you found, files created/changed\n"
        "- Be thorough but concise\n"
    )
    parts = [base, extra, f"Time: {system_time}"]
    if allowed_tools:
        parts.append(f"## Available Tools\n{allowed_tools}")
    if context:
        parts.append(f"## Context\n{context}")
    parts.append(f"## Task\n{goal}")
    if extra_instructions:
        parts.append(f"## Additional Instructions\n{extra_instructions}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 1. Context file discovery (CLAUDE.md, AGENTS.md)
# ---------------------------------------------------------------------------

def _discover_context_files(cwd: str | None = None) -> str:
    """Walk up from cwd to find project context files.
    
    Priority (first match wins):
      1. AGENTS.md / agents.md
      2. CLAUDE.md / claude.md
    """
    search_dir = Path(cwd or os.getcwd()).resolve()
    
    # Walk up to git root or filesystem root
    for parent in [search_dir, *search_dir.parents]:
        for name in ["AGENTS.md", "agents.md", "CLAUDE.md", "claude.md"]:
            candidate = parent / name
            if candidate.exists():
                try:
                    content = candidate.read_text("utf-8").strip()
                    if not content:
                        continue
                    if len(content) > _CONTEXT_FILE_MAX_CHARS:
                        content = content[:_CONTEXT_FILE_MAX_CHARS] + "\n\n[...truncated]"
                    return f"## {name}\n\n{content}"
                except Exception:
                    continue
        # Stop at filesystem root or git root
        if (parent / ".git").exists() or parent == parent.parent:
            break
    return ""


# ---------------------------------------------------------------------------
# 2. Environment hints (OS, Docker, sandbox)
# ---------------------------------------------------------------------------

def _build_environment_hints() -> str:
    """Build a block describing the execution environment."""
    lines = []
    system = platform.system()
    release = platform.release()
    
    if system == "Windows":
        lines.append(f"Host: Windows ({release})")
    elif system == "Darwin":
        mac_ver = platform.mac_ver()[0]
        lines.append(f"Host: macOS ({mac_ver or release})")
    elif system == "Linux":
        import shutil
        is_wsl = bool(shutil.which("wslpath"))
        if is_wsl:
            lines.append("Host: WSL (Windows Subsystem for Linux)")
            lines.append("The Windows host filesystem is mounted under /mnt/")
        else:
            lines.append(f"Host: Linux ({release})")
    else:
        lines.append(f"Host: {system} ({release})")
    
    lines.append(f"User home: {Path.home()}")
    lines.append(f"Workspace: {os.getcwd()}")
    
    # Docker detection
    docker_env = os.environ.get("DOCKER_HOST") or os.environ.get("SANDBOX_DIR", "")
    if docker_env:
        lines.append("Runtime: Docker sandbox available")
    else:
        lines.append("Runtime: Docker sandbox available (via docker_executor)")
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. Skills disk cache (fast cold start)
# ---------------------------------------------------------------------------

def _skills_cache_path() -> Path:
    cache_dir = Path.home() / ".testai"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / ".skills_cache.json"


def _load_skills_cache() -> list[dict[str, Any]] | None:
    path = _skills_cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
        if time.time() - data.get("timestamp", 0) < _SKILLS_CACHE_TTL:
            return data.get("skills")
    except Exception:
        pass
    return None


def _save_skills_cache(skills: list[dict[str, Any]]) -> None:
    # Phase-8 P1 #8: atomic write — write to a temp file in the same
    # directory, then ``os.replace`` onto the final path.  This prevents
    # a 0-byte file from being left on disk if the process dies mid-write.
    try:
        path = _skills_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "timestamp": time.time(),
            "skills": skills,
        }, ensure_ascii=False)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, path)
        except Exception as write_exc:
            # Best-effort cleanup of the temp file so we never leave it
            # lying around.
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise
    except Exception as exc:  # pragma: no cover — defensive
        import logging
        logging.getLogger(__name__).warning(
            "Failed to write skills cache atomically: %s", exc
        )


def _build_skills_index() -> str:
    # Try cache first
    cached = _load_skills_cache()
    if cached is not None:
        skills = cached
    else:
        skills = _scan_skills()
        if skills:
            _save_skills_cache(skills)
    
    if not skills:
        return ""
    
    lines = [
        "Before replying, scan the skills below. If one clearly matches your task, "
        "load it with `skill_view(name)` and follow its instructions.\n"
    ]
    for s in skills:
        reqs = ""
        if s.get("requires_toolsets"):
            reqs = f" [requires: {', '.join(s['requires_toolsets'])}]"
        lines.append(f"- **{s['name']}**: {s['description']}{reqs}")
    lines.append("\nOnly load a skill when it clearly applies. Do not load every skill.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shared helpers (unchanged)
# ---------------------------------------------------------------------------


def _build_mode_block(mode: str, toolsets: list[str] | None = None) -> str:
    if mode not in MODES:
        return ""
    cfg = MODES[mode]
    parts = [f"## Mode: {mode}"]
    parts.append(f"Description: {cfg['description']}")
    if toolsets:
        parts.append(f"Available toolsets: {', '.join(toolsets)}")
        all_tools = _resolve_tool_names(toolsets)
        if all_tools:
            parts.append(f"Tools: {', '.join(sorted(all_tools))}")
    return "\n".join(parts)


def _resolve_tool_names(toolsets: list[str]) -> list[str]:
    from harness.tools.toolsets import resolve_toolsets
    return resolve_toolsets(toolsets)


def _system_context() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "system_time": now.strftime("%Y-%m-%d %H:%M UTC"),
        "environment_hints": _build_environment_hints(),
    }


# ---------------------------------------------------------------------------
# Public API (unchanged signature)
# ---------------------------------------------------------------------------


def build_system_prompt(
    mode: str = "auto",
    skills_index: str = "",
    toolsets: list[str] | None = None,
    extra_context: str = "",
    template: str | None = None,
    cwd: str | None = None,
) -> str:
    ctx = _system_context()

    # Load system prompt  files for this mode
    mode_prompt_parts: list[str] = []
    for pname in system_prompts_for_mode(mode):
        content = load_prompt(pname)
        if content:
            mode_prompt_parts.append(content)
    prompts_block = "\n\n---\n\n".join(mode_prompt_parts) if mode_prompt_parts else ""

    from harness.quality_policy import get_quality_policy
    quality_block = get_quality_policy().build_prompt_block()

    return _build_prompt(
        identity=prompt_for_mode(mode),
        system_time=ctx["system_time"],
        environment_hints=ctx["environment_hints"],
        mode_block=_build_mode_block(mode, toolsets),
        project_context=_discover_context_files(cwd),
        memory=get_memory_snapshot(),
        extra_context=(
            extra_context
            + ("\n\n" + prompts_block if prompts_block else "")
            + ("\n\n" + quality_block if quality_block else "")
            + get_reflection_snapshot()
        ),
        toolsets=toolsets,
    )


def build_skills_user_message(skills_index: str | None = None) -> str:
    """Build a user message block containing the skills index.

    Injected as a user message (not system prompt) to preserve prompt caching.
    """
    index = skills_index or _build_skills_index()
    if not index:
        return ""
    return f"## Available Skills\n\n{index}"


def build_subagent_prompt(
    goal: str,
    context: str = "",
    allowed_tools: list[str] | None = None,
    extra_instructions: str = "",
    template: str | None = None,
) -> str:
    ctx = _system_context()
    return _build_subagent_prompt(
        goal=goal,
        system_time=ctx["system_time"],
        allowed_tools=", ".join(sorted(allowed_tools)) if allowed_tools else "",
        context=context,
        extra_instructions=extra_instructions,
    )

from __future__ import annotations

# Toolset used by the chat Role. The chat is read-only — its ONE
# allowed mutation is `submit_job`, which produces a JobSpec and hands
# it to the orchestrator. The chat itself never runs bash, never
# writes files, never opens PRs.
CHAT_READONLY_TOOLSET: list[str] = [
    # Internal-state read tools — the chat can introspect the system.
    "list_runs", "get_run", "get_logs", "list_testcases",
    "get_testcase", "get_run_artifacts", "search_runs",
    "get_dashboard_status", "get_coverage",
    # Chat surface read tools — introspect thread history.
    "list_chat_threads", "get_chat_thread",
    "list_chat_thread_messages", "get_chat_thread_for_run",
    # Persistent memory (Hermes pattern: MEMORY.md + USER.md per repo).
    "memory",
    # Mutations: submit, control, and inspect jobs. The chat is the
    # user's front door — they submit jobs, then ask "is it done?" or
    # "cancel that one". The chat itself never reaches into the
    # orchestrator; it just signals the JobSpecStore, and the
    # cancel_watcher / BoardWaiter do the work.
    "submit_job",
    "cancel_job", "pause_job", "resume_job", "list_jobs", "get_job_status", "comment_on_job",
    # Skill discovery — read-only listing of available skills.
    "skills_list", "skill_view",
    # Clarifying questions back to the user.
    "question",
]

TOOLSETS: dict[str, dict] = {
    "chat": {
        "description": (
            "Read-only introspection + job lifecycle handoff. The chat "
            "Role's toolset. The chat can read internal state, submit a "
            "job, and control its own jobs (cancel/pause/list/status). "
            "It never writes files, runs bash, spawns sub-agents, or "
            "opens PRs."
        ),
        "tools": list(CHAT_READONLY_TOOLSET),
        "includes": [],
    },
    "read": {
        "description": "Read-only tools for research and code analysis",
        "tools": [
            "read_file", "list_files", "glob", "grep",
            "memory", "web_search", "web_fetch",
            "skills_list", "skill_view", "skill_manage", "skill_info", "skill_evolve",
            "skill_versions", "skill_stats", "tool_search", "todo",
        ],
        "includes": [],
    },
    "write": {
        "description": "Tools that execute commands or mutate files",
        "tools": [
            "bash", "write_file", "edit_file", "apply_patch",
        ],
        "includes": [],
    },
    "intelligence": {
        "description": "Code intelligence tools for structural understanding",
        "tools": [
            "codegraph_explore", "codegraph_node", "codegraph_search",
            "codegraph_callers", "codegraph_callees",
            # Back-compat KG tools (TestAI-internal naming). Kept for
            # older agent YAMLs that reference them by old name.
            "kg_search", "kg_callers", "kg_callees", "kg_graph_status",
            # Optional semantic search over kg_embeddings (no-op if
            # the table is not initialised).
            "semantic_search",
            "lsp",
        ],
        "includes": [],
    },
    "delegate": {
        "description": "Subagent spawning, communication, and task tracking",
        "tools": ["delegate_task", "send_message", "question"],
        "includes": ["kanban"],
    },
    "healing": {
        "description": "Self-healing tools — auto-suggest locators for failing tests",
        "tools": [
            "attempt_heal",
        ],
        "includes": [],
    },
    "kanban": {
        "description": "Kanban board tools — list, create, claim, complete, and manage tasks",
        "tools": [
            "kanban_list", "kanban_show", "kanban_create",
            "kanban_assign", "kanban_start", "kanban_complete",
            "kanban_block", "kanban_unblock", "kanban_comment",
            "kanban_heartbeat", "kanban_link",
        ],
        "includes": [],
    },
    "specialized": {
        "description": "Gated tools — opt-in via Role YAML. Requires a vision-capable model for computer_use.",
        "tools": [
            "computer_use", "vision_analyze", "diagram",
            "database_query", "image_generate", "visual_diff",
        ],
        "includes": [],
    },
    "plan": {
        "description": "Plan-mode tools. Enter/exit plan mode for human-approved plans.",
        "tools": [
            "enter_plan_mode", "exit_plan_mode",
        ],
        "includes": [],
    },
    "team": {
        "description": (
            "Multi-agent team coordination — create a team, dispatch "
            "messages, track member progress, dissolve when done. "
            "Members are subagents with their own Role + toolsets."
        ),
        "tools": [
            "team_create", "team_message", "team_list_messages",
            "team_list_members", "team_member_progress", "team_dissolve",
        ],
        "includes": [],
    },
    "analysis": {
        "description": (
            "Read-only analysis tools — repo / language / tech-stack "
            "detection and CVE / dependency scanning."
        ),
        "tools": [
            "repo_analyzer", "tech_stack_detector", "detect_languages",
            "osv_check", "coverage_analyzer",
        ],
        "includes": [],
    },
    "execution": {
        "description": (
            "Code-execution and Docker inspection tools. "
            "Opt-in via Role YAML — can run arbitrary user code."
        ),
        "tools": [
            "execute_code", "docker_executor", "docker_image_list",
        ],
        "includes": [],
    },
    "shell": {
        "description": "PowerShell and notebook-edit tools. Windows-only.",
        "tools": [
            "powershell", "notebook_edit",
        ],
        "includes": [],
    },
    "persistence": {
        "description": "Save and list per-run artifacts and trajectory data.",
        "tools": [
            "artifact_save", "artifact_list", "artifact_read",
        ],
        "includes": [],
    },
    "session": {
        "description": "Per-session checkpoint save / resume.",
        "tools": [
            "checkpoint", "checkpoint_resume",
        ],
        "includes": [],
    },
    "browser": {
        "description": "Browser automation via Playwright (requires the playwright binary).",
        "tools": [
            "browser_navigate", "browser_snapshot",
        ],
        "includes": [],
    },
    "orchestrator": {
        "description": (
            "The orchestrator agent toolset. Bootstrap environment: "
            "clone repo, build KG, create kanban, delegate to coordinator. "
            "CANNOT write/edit files — that's the coordinator's job. "
            "Pattern: Hermes orchestrator → coordinator → worker delegation."
        ),
        "tools": [
            # ORCHESTRATION — the orchestrator's core job
            "orchestrate", "orchestrate_monitor",
            "delegate_task",
            # KANBAN — create initial board and tasks
            "kanban_create", "kanban_list", "kanban_complete",
            # CODE INTELLIGENCE — read-only for repo exploration
            "codegraph_explore", "codegraph_search", "codegraph_node", "codegraph_callers",
            # GITHUB — list issues, PRs during explore phase
            "github_list_issues", "github_list_prs",
            "github_get_pr_detail", "github_get_pr_files", "github_get_ci_checks",
            "github_post_comment", "github_add_labels",
            # FILESYSTEM — read-only for repo inspection
            "glob", "grep", "read_file",
            # KNOWLEDGE + MEMORY
            "memory", "skill_view", "skills_list",
            # SKILLS — create, manage, and evolve skills
            "skills_list", "skill_view", "skill_manage",
            # COMMUNICATION
            "send_message", "question", "todo",
        ],
        "includes": [],
    },
    # ------------------------------------------------------------------
    # Q5: Per-role subagent toolsets. Each subagent gets a CURATED
    # toolset so the LLM only sees tools it actually needs (Q1 root
    # cause: 79 tools at once overwhelms deepseek-v4-flash tool-calling).
    # ------------------------------------------------------------------
    "coordinator": {
        "description": (
            "Manager toolset for the orchestrator's coordinator. "
            "CAN orchestrate (task decomposition), delegate to workers, "
            "manage kanban, read code (codegraph/glob/grep), and ship "
            "(commit_and_open_pr). CANNOT write/edit files or run bash — "
            "those are delegated to bug-fixer/test-writer subagents. "
            "Pattern: Hermes openclaude coordinator-cannot-write-files."
        ),
        "tools": [
            # READ-ONLY code intelligence
            "codegraph_explore", "codegraph_search", "codegraph_node",
            "glob", "grep", "web_fetch",
            # GITHUB — list issues, PRs, get diffs, CI checks, comments, labels
            "github_list_issues", "github_list_prs",
            "github_get_pr_detail", "github_get_pr_files", "github_get_ci_checks",
            "github_post_comment", "github_add_labels",
            # ORCHESTRATION — the coordinator's core job
            "orchestrate",
            "delegate_task",
            # KANBAN — track and manage tasks
            "kanban_create", "kanban_list", "kanban_complete",
            # SKILLS — create, manage, and evolve skills
            "skills_list", "skill_view", "skill_manage",
            "skill_info", "skill_evolve",
            # SHIPPING — final step (tier-1 only)
            "commit_and_open_pr", "schedule_pr",
            # KNOWLEDGE — KG updates after workers finish
            "kg_refresh",
            # TRACKING — in-session task list
            "todo", "question",
        ],
        "includes": [],
    },
    "test-writer": {
        "description": "Subagent for writing tests. Read + write tests only.",
        "tools": [
            "bash", "read_file", "write_file",
            "glob", "grep",
            "codegraph_search",
        ],
        "includes": [],
    },
    "bug-fixer": {
        "description": (
            "Subagent for fixing one bug at a time. Coordinator-level tools "
            "minus delegate_task / commit_and_open_pr / schedule_pr / task_*."
        ),
        "tools": [
            "bash", "write_file", "edit_file", "apply_patch",
            "glob", "grep",
            "codegraph_explore", "codegraph_search", "codegraph_node",
            "kanban_list", "kanban_complete",
            "kg_refresh", "attempt_heal",
            "osv_check", "web_fetch",
            "todo", "question",
        ],
        "includes": [],
    },
    "code-reviewer": {
        "description": "Read-only review. No writes, no shell. Has GitHub tools for PR review.",
        "tools": [
            "read_file", "glob", "grep", "codegraph_explore", "web_fetch",
            "github_get_pr_detail", "github_get_pr_files", "github_get_ci_checks",
        ],
        "includes": [],
    },
    "security-auditor": {
        "description": "Read + CVE scan. No writes, no shell.",
        "tools": [
            "read_file", "glob", "grep", "osv_check", "web_fetch",
        ],
        "includes": [],
    },
    "docs-writer": {
        "description": "Minimal docs author: read + write markdown only.",
        "tools": ["read_file", "write_file", "glob"],
        "includes": [],
    },
}

MODES: dict[str, dict] = {
    "chat": {
        "description": (
            "General-purpose AI assistant. Helps with any task: "
            "coding, analysis, debugging, testing, writing, and more. "
            "Can use tools when needed to read files, run commands, "
            "or interact with the system."
        ),
        "toolsets": ["chat"],
        "prompt": (
            "You are a helpful AI assistant. You can help with any task "
            "including coding, analysis, debugging, testing, writing, "
            "and general questions. Be concise, direct, and helpful. "
            "When the user asks you to do something, do it directly "
            "without unnecessary preamble."
        ),
        "system_prompts": ["chat-role"],
    },
}
"""Available chat-surface modes.

The TestAI product has **two surfaces**, not one with modes:

  - **Chat** — the read-only triage surface the user talks to. The LLM
    infers intent from the message. This is the only surface that
    goes through `MODES`.
  - **Job-runner** — the autonomous surface driven by
    `OrchestratorEngine.run_job_spec()`. It doesn't go through
    `MODES` at all; the orchestrator hands the coordinator a fixed
    `toolsets=["orchestrator"]` and a tier-aware goal string. See
    `harness/orchestrator.py`.

The historical `auto` / `ask` / `architect` / `debug` / `plan` /
`explore` / `batch` / `review` / `custom` mode entries were removed:
competitor research (Testim, Mabl, testRigor, Claude Code, Cursor)
shows that user-selectable agent personas in a chat surface are
uncommon and the LLM can infer the right behaviour. The `custom`
mode was unreferenced. Any code that still passes a dropped mode
name to `toolsets_for_mode` or `prompt_for_mode` falls back to
`chat`, since the chat surface is the only one that consumes
these lookups.
"""


def resolve_toolsets(names: list[str]) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        ts = TOOLSETS.get(name)
        if ts:
            resolved.extend(ts["tools"])
            for inc in ts.get("includes", []):
                if inc not in seen:
                    seen.add(inc)
                    sub = TOOLSETS.get(inc)
                    if sub:
                        resolved.extend(sub["tools"])
        else:
            resolved.append(name)
    return resolved


# P0 audit fix 2026-06-23: 17 agent .md role files use short tool
# names (``read`` / ``list`` / ``write`` / ``edit``) that the
# registry doesn't expose — the actual tool names are
# ``read_file`` / ``list_files`` / ``write_file`` / ``edit_file``.
# The orchestrator's kanban workers path passes the YAML list
# straight to ``agent_factory(allowed_tools=...)`` and would
# silently end up with zero tools. Translate here. The registry
# is the source of truth: if a name is already a real tool, it's
# left alone.
_SHORT_TOOL_NAME_ALIASES = {
    "read": "read_file",
    "list": "list_files",
    "write": "write_file",
    "edit": "edit_file",
    "patch": "apply_patch",
    "exec": "bash",
    "search": "codegraph_search",
    "kg": "kg_search",
    "graph": "codegraph_explore",
    "node": "codegraph_node",
    "callers": "codegraph_callers",
    "callees": "codegraph_callees",
}


def translate_short_tool_names(names: list[str]) -> list[str]:
    """Map the short tool names used in 17 role YAMLs to real registry names.

    Idempotent: already-translated names pass through unchanged. Unknown
    names pass through unchanged so the registry's
    ``list_specs`` can drop them (as before). P0 audit fix 2026-06-23.
    """
    if not names:
        return names
    out: list[str] = []
    for n in names:
        if not isinstance(n, str):
            out.append(n)
            continue
        out.append(_SHORT_TOOL_NAME_ALIASES.get(n, n))
    return out


def toolsets_for_mode(mode: str) -> list[str]:
    """Return the toolsets for a chat-surface mode.

    The chat surface is the only consumer of this function. Unknown
    mode names (legacy `auto` / `ask` / etc., or empty strings) fall
    back to the chat toolset rather than raising — the chat UI may
    still pass legacy values from old tabs.
    """
    cfg = MODES.get(mode)
    if not cfg:
        return resolve_toolsets(MODES["chat"]["toolsets"])
    return resolve_toolsets(cfg["toolsets"])


def prompt_for_mode(mode: str) -> str:
    """Return the identity string for a chat-surface mode.

    Unknown mode names fall back to the chat prompt. The orchestrator
    surface does not call this; it injects the goal directly.
    """
    cfg = MODES.get(mode)
    if not cfg:
        return MODES["chat"]["prompt"]
    return cfg["prompt"]


def system_prompts_for_mode(mode: str) -> list[str]:
    """Return the system-prompt filenames for a chat-surface mode.

    Unknown mode names return an empty list — the chat Role's
    identity is sufficient on its own. The orchestrator surface
    injects its own system prompts via the goal string, not this
    function.
    """
    cfg = MODES.get(mode)
    if not cfg:
        return []
    return cfg.get("system_prompts", [])

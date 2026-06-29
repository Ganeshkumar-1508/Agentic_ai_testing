"""Orchestrator tool — dynamic task decomposition via coordinator agent.

Magentic-One style: orchestrator analyzes a request/PR, decomposes into
kanban tasks with per-task agent_role + tools + skills, and creates them
with dependencies. The coordinator agent handles execution.

Two tools:
  - orchestrate:      Decompose a goal into kanban tasks, create board + tasks
  - orchestrate_monitor: Check board progress, re-plan if stalled
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry
from harness.memory.db_context import get_db

logger = logging.getLogger(__name__)

_DECOMPOSE_SYSTEM_PROMPT = """You are a task decomposer. Your job is to break a goal into 8-15 self-contained subtasks.

TASK COUNT GUIDELINES:
- Simple bug fix (1-2 files): 8-10 tasks
- Medium feature (3-5 files): 10-12 tasks  
- Complex feature/refactor (6+ files): 12-15 tasks
- Always include 5 parallel explore tasks at the start

PARALLEL EXECUTION STRATEGY:
- First 5 tasks should be INDEPENDENT explore tasks (parents: []) that can run in parallel
- These explore different aspects: call graph, code patterns, tests, git history, dependencies
- After explore, add sequential phases: triage → implement → test → verify → review

For each subtask, pick the best agent from the AVAILABLE AGENTS list below.
Each subtask must be SELF-CONTAINED — include file paths, what to change,
and how to verify. The worker must be able to act WITHOUT asking for clarification.

AVAILABLE AGENTS:
{agents}

Return ONLY a JSON array of task objects. Each task:
- title: short imperative name (<=80 chars)
- description: detailed spec the worker can follow independently (include file paths, expected changes, verification)
- agent_role: name of the agent from AVAILABLE AGENTS
- tools: tool names the agent needs
- parents: zero-based indices this depends on ([] if independent)

CRITICAL: First 5 tasks MUST have parents: [] (no dependencies) so they run in parallel."""


_SYSTEM_PROMPT_MARKERS = [
    "You are a task decomposer", "system prompt", "system prompt",
    "AVAILABLE AGENTS", "CRITICAL:", "PARALLEL EXECUTION",
    "TASK COUNT GUIDELINES", "Return ONLY a JSON",
]


def _sanitize_task_title(title: str) -> str:
    """Strip system prompt content that may leak into task titles."""
    cleaned = title.strip()[:120]
    for marker in _SYSTEM_PROMPT_MARKERS:
        if marker.lower() in cleaned.lower():
            cleaned = cleaned.replace(marker, "").strip()
    return cleaned if cleaned else "Untitled task"


def _validate_decomposition(goal: str, tasks: list[dict]) -> list[dict] | None:
    """Validate that tasks contain entities from the goal. Returns tasks or None."""
    if not tasks:
        return None

    entities: set[str] = set()
    entities.update(re.findall(r'PR\s*#?(\d+)', goal, re.IGNORECASE))
    entities.update(re.findall(r'issue\s*#?(\d+)', goal, re.IGNORECASE))
    entities.update(re.findall(r'(\w+\.\w+)', goal))
    entities.update(re.findall(r'[\w/]+\.\w+', goal))
    entities.update(re.findall(r'[a-z]+(?:-[a-z]+)+', goal))

    goal_lower = goal.lower()
    goal_words = {w for w in re.findall(r'[a-zA-Z_]\w{3,}', goal_lower)}

    if not entities and not goal_words:
        return tasks

    task_texts = []
    for t in tasks:
        title = (t.get("title") or t.get("description", ""))
        desc = (t.get("description") or "")
        task_texts.append(f"{title} {desc}")

    combined = " ".join(task_texts).lower()

    entity_hits = sum(1 for e in entities if e.lower() in combined)
    word_hits = sum(1 for w in goal_words if w in combined)

    hit_ratio = (entity_hits + word_hits) / max(len(entities) + len(goal_words or {1}), 1)

    if hit_ratio < 0.1:
        logger.warning(
            "Decomposition hallucination: goal entities not reflected in tasks "
            "(ratio=%.2f, entities=%d, tasks=%d)",
            hit_ratio, len(entities), len(tasks),
        )
        return None

    return tasks


async def _llm_decompose(goal: str, repo_context: str, available_agents: list[dict]) -> list[dict]:
    """Call an LLM to decompose a goal into structured subtasks.

    Returns list of dicts: {title, description, agent_role, tools, skills, depends_on}
    """
    from harness.api.state import get_llm

    db = get_db()
    if not db:
        return _default_decomposition(goal, available_agents)

    # Use the shared LLM router that was configured during startup
    llm = get_llm()
    if not llm:
        logger.warning("Shared LLM router not available, using default decomposition")
        return _default_decomposition(goal, available_agents)

    # Build agents roster from discovered agent .md files
    from harness.agent_discovery import discover_agents
    discovered = discover_agents()
    if discovered:
        agents_str = "\n".join(
            f"- {name}: {a.description} (tools: {', '.join(a.tools[:6])})"
            for name, a in sorted(discovered.items())
        )
    else:
        agents_str = "\n".join(
            f"- {a.get('role', a.get('name', '?'))}: {a.get('description', '')} "
            f"(tools: {', '.join(a.get('allowed_tools', a.get('tools', []))[:5])})"
            for a in available_agents[:10]
        )

    # Extract explore findings from repo_context if available
    explore_section = ""
    try:
        rc = json.loads(repo_context) if isinstance(repo_context, str) else (repo_context or {})
        if isinstance(rc, dict) and rc.get("explore"):
            explore_section = f"\nEXPLORE FINDINGS (from KG query):\n{rc['explore']}\n"
    except Exception:
        pass

    system_prompt = _DECOMPOSE_SYSTEM_PROMPT.format(agents=agents_str)
    user_msg = f"GOAL: {goal}\n\nREPO CONTEXT: {repo_context or 'Not provided'}{explore_section}"

    try:
        from harness.llm import ChatMessage
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_msg),
        ]
        response = await llm.chat(messages)
        text = response.content if hasattr(response, "content") else str(response)
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0] if "```" in text else text
            text = text.strip()
        # Some models (DeepSeek) put reasoning first — find the first [ or {
        json_start = min(
            text.find("["), text.find("{"),
            key=lambda x: x if x >= 0 else len(text),
        ) if any(c in text for c in "[{") else 0
        if json_start > 0:
            text = text[json_start:]
        tasks = json.loads(text)
        if isinstance(tasks, dict) and "tasks" in tasks:
            tasks = tasks["tasks"]
        if isinstance(tasks, list):
            validated = _validate_decomposition(goal, tasks)
            if validated:
                return validated
        return _default_decomposition(goal, available_agents)
    except Exception as e:
        logger.warning("LLM decomposition failed: %s — using defaults", e)
        return _default_decomposition(goal, available_agents)


def _default_decomposition(goal: str, available_agents: list[dict]) -> list[dict]:
    """Fallback decomposition when LLM is unavailable.
    
    Creates 12-15 tasks with 5 parallel explore tasks (no dependencies),
    then sequential triage/fix/verify phases. More granular breakdown
    allows better parallelization and specialized agent assignment.
    """
    goal_short = goal[:60]
    goal_medium = goal[:200]
    
    return [
        # Phase 1: 5 parallel explore tasks (no parents = can run in parallel)
        {
            "title": f"Explore: Trace call graph for {goal_short}",
            "description": f"Use codegraph_explore to trace the call graph related to: {goal_medium}. Identify all functions, classes, and modules involved. Report file paths and line numbers.",
            "agent_role": "explore",
            "tools": ["codegraph_explore", "codegraph_search", "codegraph_callers", "glob", "grep", "read"],
            "parents": [],
        },
        {
            "title": f"Explore: Search codebase for related patterns",
            "description": f"Use codegraph_search and grep to find all code patterns related to: {goal_medium}. Look for similar implementations, edge cases, and related functionality across the codebase.",
            "agent_role": "explore",
            "tools": ["codegraph_search", "codegraph_explore", "grep", "glob", "read"],
            "parents": [],
        },
        {
            "title": f"Explore: Find test coverage gaps",
            "description": f"Search for existing tests related to: {goal_medium}. Use glob to find test files, grep to search for relevant test cases. Identify what's tested and what's missing.",
            "agent_role": "explore",
            "tools": ["glob", "grep", "read", "codegraph_search"],
            "parents": [],
        },
        {
            "title": f"Explore: Check git history and recent changes",
            "description": f"Use bash to run 'git log --oneline -20' and 'git log --all --grep=\"{goal_short[:30]}\"' to find recent changes related to this issue. Check if this is a regression or new issue.",
            "agent_role": "explore",
            "tools": ["bash", "read", "grep"],
            "parents": [],
        },
        {
            "title": f"Explore: Analyze dependencies and imports",
            "description": f"Use codegraph_callers and codegraph_callees to map the dependency tree for code related to: {goal_medium}. Identify which modules import the affected code and what could break.",
            "agent_role": "explore",
            "tools": ["codegraph_callers", "codegraph_callees", "codegraph_explore", "grep", "read"],
            "parents": [],
        },
        # Phase 2: Triage (depends on all 5 explore tasks)
        {
            "title": "Analyze and plan",
            "description": "Review all 5 explore findings. Synthesize the information, identify root cause, trace impact across the codebase, and produce a structured fix plan with exact file paths and proposed changes. Use memory tool to save findings.",
            "agent_role": "triage",
            "tools": ["codegraph_explore", "codegraph_callers", "read", "grep", "memory"],
            "parents": [0, 1, 2, 3, 4],
        },
        # Phase 3: Implement (split into 2-3 tasks for parallel execution)
        {
            "title": f"Implement core fix: {goal_short}",
            "description": f"Implement the core fix based on the triage plan. Read the plan from memory. Make changes to the primary affected files. Focus on the root cause identified by triage.",
            "agent_role": "fix",
            "tools": ["read", "write", "edit", "bash", "grep", "glob", "codegraph_callers", "memory"],
            "parents": [5],
        },
        {
            "title": f"Implement related changes and edge cases",
            "description": f"Based on triage findings, implement related changes in dependent modules. Handle edge cases identified during exploration. Update any affected interfaces or APIs.",
            "agent_role": "fix",
            "tools": ["read", "write", "edit", "bash", "grep", "glob", "codegraph_callers"],
            "parents": [5],
        },
        {
            "title": "Update configuration and documentation",
            "description": "Update any configuration files, environment variables, or documentation affected by the changes. Check README, CHANGELOG, and inline comments.",
            "agent_role": "doc-updater",
            "tools": ["read", "write", "edit", "glob", "grep"],
            "parents": [5],
        },
        # Phase 4: Write regression test (depends on fix)
        {
            "title": "Write regression test",
            "description": "Write a regression test that reproduces the bug and verifies the fix. Place the test in the appropriate test directory. Ensure it follows the project's test conventions.",
            "agent_role": "test-writer",
            "tools": ["read", "write", "glob", "grep", "bash", "codegraph_search"],
            "parents": [6, 7],
        },
        {
            "title": "Write integration tests",
            "description": "Write integration tests that verify the fix works end-to-end. Test interactions between modules. Ensure backward compatibility.",
            "agent_role": "test-writer",
            "tools": ["read", "write", "glob", "grep", "bash"],
            "parents": [6, 7],
        },
        # Phase 5: Verify (depends on tests)
        {
            "title": "Run unit tests and verify fix",
            "description": "Run the unit test suite (or relevant subset) to ensure the fix works and doesn't break anything. Capture evidence: test output, coverage report. Report pass/fail status.",
            "agent_role": "verify",
            "tools": ["bash", "read", "grep", "glob"],
            "parents": [9, 10],
        },
        {
            "title": "Run integration tests and performance checks",
            "description": "Run integration tests to verify end-to-end functionality. Check for performance regressions. Validate that the fix doesn't introduce new issues.",
            "agent_role": "verify",
            "tools": ["bash", "read", "grep", "glob"],
            "parents": [9, 10],
        },
        # Phase 6: Security audit (depends on verify)
        {
            "title": "Security audit",
            "description": "Review the changes for security vulnerabilities. Check for injection attacks, authentication bypass, data exposure. Use osv_check if available to scan for known vulnerabilities.",
            "agent_role": "security-auditor",
            "tools": ["read", "grep", "glob", "codegraph_search", "osv_check"],
            "parents": [11, 12],
        },
        # Phase 7: Code review (depends on security)
        {
            "title": "Code review",
            "description": "Review the changes for code quality, security, and adherence to project conventions. Use codegraph_explore to check if the changes follow existing patterns. Report any issues found.",
            "agent_role": "code-reviewer",
            "tools": ["read", "glob", "grep", "codegraph_explore", "codegraph_search"],
            "parents": [13],
        },
    ]


async def _get_available_agents() -> list[dict]:
    """Get available agent definitions from AgentStore (DB) or AgentConfig (filesystem)."""
    try:
        db = get_db()
        if db:
            from harness.store.adapters.postgres import PostgresAgentStore
            store = PostgresAgentStore(db)
            agents = await store.list_agents()
            if agents:
                return [a.__dict__ for a in agents]
    except Exception as e:
        logger.debug("DB agent list failed: %s", e)

    try:
        from harness.agent_config import AgentStore
        fs_store = AgentStore()
        agents = fs_store.list_agents()
        return [a.to_dict() for a in agents]
    except Exception as e:
        logger.debug("Filesystem agent list failed: %s", e)

    return []


async def _create_kanban_board(db, name: str, description: str = "", session_id: str = "") -> str:
    """Create a kanban board for this orchestration run.

    C03: ``session_id`` is stashed in the board's ``config`` JSONB so
    the kanban service can route ``board.completed`` / ``board.failed``
    events to the orchestrator's EventSourceSink subscription. Without
    this, the event is broadcast to every subscriber and the
    orchestrator's waiter would have to filter by ``board_id`` (still
    works, just more chatty on the SSE feed).
    """
    config = {"source": "orchestrator", "failure_limit": 3}
    if session_id:
        config["session_id"] = session_id
    # P0 audit fix 2026-06-23: use the canonical 7-column set that
    # matches the API default and the frontend default. The previous
    # 6-column set (``blocked`` instead of ``flaky_heat``/``triage``)
    # caused the dashboard to render the orchestrator-created board
    # with two missing columns. ``blocked`` is still available as a
    # transient state inside ``review``/``done`` via the
    # ``column_name`` column on the task; we don't need a dedicated
    # column for it.
    row = await db.fetchrow(
        "INSERT INTO kanban_boards (name, description, columns, config) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        name, description,
        json.dumps([
            "triage", "backlog", "ready", "in_progress",
            "review", "done", "flaky_heat",
        ]),
        json.dumps(config),
    )
    return row["id"]


async def _first_board_column(db, board_id: str) -> str:
    """Return the first column name for a kanban board."""
    row = await db.fetchrow("SELECT columns FROM kanban_boards WHERE id = $1", board_id)
    if row:
        cols = row["columns"]
        if isinstance(cols, str):
            cols = json.loads(cols)
        if isinstance(cols, list) and cols:
            return cols[0]
    return "backlog"


async def _create_kanban_task(db, board_id: str, task: dict, task_ids: list[str]) -> str:
    """Create a single kanban task with index-based parent deps. Returns task id."""
    parent_indices = task.get("parents", [])
    agent_role = task.get("agent_role", task.get("role", "worker"))
    tools = task.get("tools", [])
    tags = f"agent:{agent_role}" + (f",tools:{','.join(tools[:5])}" if tools else "")
    default_col = await _first_board_column(db, board_id)

    row = await db.fetchrow(
        """INSERT INTO kanban_tasks (board_id, title, description, column_name, priority, tags,
           model_override, toolset_override, agent_type)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
        board_id,
        _sanitize_task_title(task.get("title", "Untitled task")),
        task.get("description", ""),
        default_col if parent_indices else "ready",
        task.get("priority", "p2"),
        tags,
        task.get("model", ""),
        json.dumps(tools) if tools else "",
        agent_role,
    )
    task_id = row["id"]
    task_ids.append(task_id)

    # Resolve parent indices to actual task IDs
    for idx in parent_indices:
        if idx < len(task_ids):
            parent_id = task_ids[idx]
            await db.execute(
                "INSERT INTO kanban_dependencies (task_id, depends_on_task_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                task_id, parent_id,
            )
        else:
            logger.warning("Invalid parent index %d for task '%s'", idx, task.get("title", ""))

    await db.execute(
        "INSERT INTO kanban_events (board_id, task_id, event_type, payload) VALUES ($1, $2, $3, $4)",
        board_id, task_id, "task.created",
        json.dumps({"title": task["title"], "agent_role": agent_role, "tools": tools}),
    )
    return task_id


async def _explore_codebase(goal: str) -> str:
    """Multi-phase codebase exploration before task decomposition.

    Phase 1 — Parallel multi-hop explore agents (Fan-Out):
      Each agent runs in a loop, recursively following findings deeper.
      If a relevant function is found, it traces callers/callees deeper.
      If results are thin, it retries with broader search terms.

    Phase 2 — Deep Analyzer (Sync):
      Synthesizes all explore results into a structured report for decomposition.

    Greptile v3 "detective" + AgentOrchestra hierarchical pattern.
    """
    from harness.tools.registry import registry as _reg

    # Extract keywords for focused exploration
    _stopwords = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "with",
                  "and", "or", "is", "are", "was", "be", "fix", "bug", "add",
                  "new", "implement", "change", "update", "remove", "test"}
    keywords = [w.lower() for w in re.findall(r'\w{3,}', goal) if w.lower() not in _stopwords]
    keywords = keywords[:3]
    kw_str = ", ".join(keywords) if keywords else goal[:60]

    dt = _reg.get("delegate_task")
    if not dt:
        return ""

    # ── Phase 1: Parallel multi-hop explore agents ──
    # Uses Claude Code's battle-tested explore prompt (agent-prompt-explore.md)
    # with TestAI-specific CodeGraph instructions appended.

    from harness.prompts import load_prompt as _load_prompt
    _explore_base = _load_prompt("agent-prompt-explore") or (
        "You are a codebase exploration specialist. Read-only search and analyze."
    )

    _cg_instructions = (
        f"\n\nTASK: {goal}\nKEYWORDS: {kw_str}\n\n"
        f"TestAI-specific tools available:\n"
        f"- kg_search, kg_callers, kg_callees — CodeGraph symbol search\n"
        f"- glob, grep, read_file — standard file operations\n\n"
        f"Approach: Search with CodeGraph first, fall back to grep+glob. "
        f"Trace callers 2-3 levels deep. Read key files. Report findings directly."
    )
    explore_tasks = [
        {"goal": f"{_explore_base}{_cg_instructions}\nFOCUS: Symbol search for '{kw_str}'. "
                 f"Search broadly, follow callers/callees.",
         "toolsets": ["read", "intelligence"], "role": "leaf"},
        {"goal": f"{_explore_base}{_cg_instructions}\nFOCUS: Test analysis — find test files, "
                 f"map each to source it tests. "
                 f"Use glob for test patterns (*.test.*, *_test.*, test_*, spec_*).",
         "toolsets": ["read", "intelligence"], "role": "leaf"},
        {"goal": f"{_explore_base}{_cg_instructions}\nFOCUS: Dependency tracing for '{kw_str}'. "
                 f"Find entry points, trace callees 3 levels deep.",
         "toolsets": ["read", "intelligence"], "role": "leaf"},
        {"goal": f"{_explore_base}{_cg_instructions}\nFOCUS: Git history — 'git log --oneline -30' "
                 f"and 'git log --all --oneline --grep={kw_str}'. "
                 f"Read diff of most relevant commit.",
         "toolsets": ["read"], "role": "leaf"},
    ]

    try:
        # Q5: explore subagents use the new "coordinator" toolset (read +
        # intelligence) so the LLM only sees tools it actually needs.
        # Replaces the older blanket ["read"] which omitted codegraph.
        fan_out_result = await dt.run(tasks=explore_tasks, toolsets=["coordinator"], role="orchestrator")
        combined = fan_out_result.output if hasattr(fan_out_result, "output") else str(fan_out_result)
    except Exception as e:
        logger.warning("Phase 1 explore failed: %s", e)
        combined = ""

    # ── Phase 2: Deep Analyzer — synthesize findings ──

    if combined and len(combined) > 200:
        try:
            analyzer_goal = (
                f"You are a Deep Analyzer. Synthesize exploration results into a precise "
                f"task specification. Never delegate understanding — read the findings, "
                f"understand them, and produce a structured plan.\n\n"
                f"ORIGINAL TASK: {goal}\n\n"
                f"EXPLORATION RESULTS:\n{combined[:4000]}\n\n"
                f"Return a structured specification with:\n"
                f"- KEY FILES: file paths with 1-line description of role and why relevant\n"
                f"- KEY SYMBOLS: functions/classes, line numbers, what they do\n"
                f"- TEST COVERAGE: which tests exist for affected code\n"
                f"- DEPENDENCIES: call chains between files\n"
                f"- ARCHITECTURE: how this fits into the overall system\n"
                f"- RISK AREAS: what could break if changed"
            )
            # Q5: analyzer uses the focused bug-fixer toolset — needs read + KG,
            # not the full coordinator set.
            result = await dt.run(goal=analyzer_goal, toolsets=["bug-fixer"], role="leaf")
            synthesized = result.output if hasattr(result, "output") else str(result)
            return f"EXPLORE FINDINGS:\n{combined[:2000]}\n\nDEEP ANALYSIS:\n{synthesized[:3000]}"
        except Exception as e:
            logger.warning("Phase 2 analyzer failed: %s", e)

    return combined[:3000] if combined else ""


async def cmd_orchestrate(goal: str, repo_context: str = "", board_name: str = "", session_id: str = "") -> str:
    """Decompose a goal into kanban tasks and create the board.

    Before decomposition, runs parallel KG queries to gather code insight
    (Option B — orchestrator drives exploration).

    C03: ``session_id`` is threaded into the board's ``config.session_id``
    so the kanban service can route ``board.completed`` /
    ``board.failed`` events to the orchestrator's EventSourceSink
    subscription. Optional — omitting it falls back to broadcast
    (every subscriber sees the event and filters by board_id).

    Returns JSON with board_id and task list.
    """
    db = get_db()
    if not db:
        return json.dumps({"error": "Database not connected"})

    # Orchestrator-driven exploration: query KG in parallel before decomposing
    explore_results = await _explore_codebase(goal)
    if explore_results:
        existing = json.loads(repo_context) if repo_context else {}
        if isinstance(existing, dict):
            existing["explore"] = explore_results
        repo_context = json.dumps(existing) if isinstance(existing, dict) else explore_results

    available_agents = await _get_available_agents()
    decomposed = await _llm_decompose(goal, repo_context, available_agents)
    if not decomposed:
        return json.dumps({"error": "Task decomposition returned no tasks"})

    # Validate DAG — detect cycles via topological sort
    in_degree = [len(t.get("parents", [])) for t in decomposed]
    queue = [i for i, d in enumerate(in_degree) if d == 0]
    sorted_count = 0
    while queue:
        idx = queue.pop(0)
        sorted_count += 1
        for child_idx, t in enumerate(decomposed):
            if idx in t.get("parents", []):
                in_degree[child_idx] -= 1
                if in_degree[child_idx] == 0:
                    queue.append(child_idx)

    if sorted_count != len(decomposed):
        logger.warning("DAG cycle detected in task decomposition — falling back to sequential")
        for t in decomposed:
            t["parents"] = [i for i in range(decomposed.index(t))]

    name = board_name or f"Orchestration: {goal[:60]}"
    board_id = await _create_kanban_board(db, name, goal, session_id=session_id)
    created = []
    task_ids: list[str] = []
    for task in decomposed:
        task_id = await _create_kanban_task(db, board_id, task, task_ids)
        created.append({"id": task_id, "title": task.get("title", ""), "agent_role": task.get("agent_role", "worker")})

    return json.dumps({
        "board_id": board_id,
        "board_name": name,
        "task_count": len(created),
        "tasks": created,
        "status": "created",
    })


async def cmd_orchestrate_monitor(board_id: str, max_wait_seconds: int = 300) -> str:
    """Check kanban board progress. Returns current state of all tasks.
    
    If all tasks are done, returns completed status.
    If tasks are blocked, returns blocked status for re-planning.
    """
    db = get_db()
    if not db:
        return json.dumps({"error": "Database not connected"})

    tasks = await db.fetch(
        "SELECT id, title, column_name, tags, failure_count, result_summary "
        "FROM kanban_tasks WHERE board_id = $1 ORDER BY created_at",
        board_id,
    )
    task_list = []
    for t in tasks:
        task_list.append({
            "id": t["id"],
            "title": t["title"],
            "status": t["column_name"],
            "tags": t["tags"] or "",
            "failure_count": t["failure_count"] or 0,
            "result_summary": t["result_summary"] or "",
        })

    statuses = [t["status"] for t in task_list]
    all_done = all(s == "done" for s in statuses)
    any_blocked = any(s == "blocked" for s in statuses)
    any_failed = any(s == "blocked" for t in task_list if t.get("failure_count", 0) > 2)
    any_running = any(s in ("in_progress", "ready", "backlog") for s in statuses)

    if all_done:
        return json.dumps({"board_id": board_id, "status": "completed", "tasks": task_list})
    if any_failed:
        stalled = [t for t in task_list if t.get("failure_count", 0) > 2 and t["status"] == "blocked"]
        return json.dumps({"board_id": board_id, "status": "stalled", "stalled_tasks": stalled, "tasks": task_list})
    if any_blocked:
        blocked = [t for t in task_list if t["status"] == "blocked"]
        return json.dumps({"board_id": board_id, "status": "blocked", "blocked_tasks": blocked, "tasks": task_list})
    if any_running:
        return json.dumps({"board_id": board_id, "status": "in_progress", "tasks": task_list})

    return json.dumps({"board_id": board_id, "status": "unknown", "tasks": task_list})


# ---------------------------------------------------------------------------
# Tool classes
# ---------------------------------------------------------------------------


class OrchestrateTool(BaseTool):
    name = "orchestrate"
    description = (
        "Decompose a goal, PR, or user request into kanban subtasks with "
        "per-task agent assignments and dependencies. Creates a kanban board "
        "with tasks. The coordinator agent manages execution via delegate_task and todo. "
        "Returns board_id and task list."
    )
    default_level = "allow"
    capabilities = ["can_orchestrate"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The task goal, PR description, or user request to decompose",
                    },
                    "repo_context": {
                        "type": "string",
                        "description": "Optional repo context: files, tech stack, branch info",
                    },
                    "board_name": {
                        "type": "string",
                        "description": "Optional name for the kanban board",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional orchestrator session id. Stashed on the board's config so board.completed / board.failed events can be routed to this session's EventSourceSink subscription. Falls back to broadcast when omitted.",
                    },
                },
                "required": ["goal"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        goal = kwargs.get("goal", "")
        repo_context = kwargs.get("repo_context", "")
        board_name = kwargs.get("board_name", "")
        session_id = kwargs.get("session_id", "")
        if not goal:
            return ToolResult(success=False, output="Goal is required", error="missing_goal")
        result = await cmd_orchestrate(goal, repo_context, board_name, session_id=session_id)
        return ToolResult(success=True, output=result)


class OrchestrateMonitorTool(BaseTool):
    name = "orchestrate_monitor"
    description = (
        "Check the progress of a kanban board created by orchestrate. "
        "Returns current status of all tasks. If stalled/blocked, the "
        "orchestrator should re-plan with orchestrate."
    )
    default_level = "allow"
    capabilities = ["can_orchestrate"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "board_id": {
                        "type": "string",
                        "description": "The board ID to check",
                    },
                    "max_wait_seconds": {
                        "type": "integer",
                        "description": "Max seconds to wait for completion (default 300)",
                    },
                },
                "required": ["board_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        board_id = kwargs.get("board_id", "")
        max_wait = int(kwargs.get("max_wait_seconds", 300))
        if not board_id:
            return ToolResult(success=False, output="Board ID is required", error="missing_board_id")
        result = await cmd_orchestrate_monitor(board_id, max_wait)
        return ToolResult(success=True, output=result)


# ---------------------------------------------------------------------------
# Agent dispatch tool (Three-tier autonomous dispatch)
# ---------------------------------------------------------------------------


class ResolveAgentTool(BaseTool):
    name = "resolve_agent"
    description = (
        "Given a task goal, autonomously select the best agent to handle it. "
        "Uses three-tier dispatch: explicit @mention → TF-IDF similarity → LLM classifier. "
        "Returns the agent role, confidence score, and which tier matched."
    )
    default_level = "allow"
    capabilities = ["can_orchestrate"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The task goal or description"},
            },
            "required": ["goal"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        goal = kwargs.get("goal", "")
        if not goal:
            return ToolResult(success=False, output="Goal is required", error="missing_goal")
        from harness.dispatcher import resolve_agent
        result = await resolve_agent(goal)
        return ToolResult(success=True, output=json.dumps(result, indent=2))


# Register tools
registry.register(OrchestrateTool(), toolset="delegate")
registry.register(OrchestrateMonitorTool(), toolset="delegate")
registry.register(ResolveAgentTool(), toolset="delegate")

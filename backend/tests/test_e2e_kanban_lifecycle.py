"""E2E: repo → explore → triage → kanban board → dispatch → fix → review → done/blocked.

Simulates the full agentic pipeline:
  1. Analyze remote repo (mocked GitHub API)
  2. Create kanban board + triage tasks from repo issues
  3. Explore codebase via knowledge graph (mocked)
  4. Auto-triage tasks via LLM (mocked)
  5. Claim → work → complete → review lifecycle
  6. Blocked path — task failure → blocked column
  7. Board stats reflects all states
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Reusable fake DB with kanban table support
# ---------------------------------------------------------------------------

class Row(dict):
    """Fake asyncpg Row — supports .get() and bracket access."""
    def get(self, key, default=None):
        return super().get(key, default)


class FakeKanbanDB:
    """In-memory fake for kanban-related DB queries.

    Supports: boards, tasks, events, agent_log, dependencies, notifications.
    """

    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []
        self._boards: list[dict] = []
        self._tasks: list[dict] = []
        self._events: list[dict] = []
        self._logs: list[dict] = []
        self._deps: list[dict] = []
        self._next_task_id = 1
        self._next_event_id = 1
        self._next_board_id = 1

    # -- helpers --

    def _add_board(self, **overrides) -> dict:
        b = {
            "id": str(self._next_board_id),
            "name": "test-board",
            "description": "e2e test board",
            "columns": json.dumps(["backlog", "ready", "in_progress", "review", "done", "blocked"]),
            "wip_limits": json.dumps({"in_progress": 3}),
            "config": json.dumps({"source": "e2e-test"}),
            "created_at": None,
            **overrides,
        }
        self._next_board_id += 1
        self._boards.append(b)
        return b

    def _add_task(self, **overrides) -> dict:
        t = {
            "id": str(self._next_task_id),
            "board_id": "1",
            "title": "test task",
            "description": "",
            "column_name": "backlog",
            "priority": "p2",
            "tags": "",
            "assigned_to": "",
            "failure_count": 0,
            "claim_token": None,
            "claimed_at": None,
            "claim_expires_at": None,
            "pipeline_run_id": "",
            "coverage_file": "",
            "flaky_test_name": "",
            "timebox_seconds": 0,
            "estimate_minutes": 0,
            "result_summary": "",
            "needs_review": False,
            "review_status": None,
            "review_notes": "",
            "reviewed_by": "",
            "deadline": None,
            "sprint": "",
            "model_override": "",
            "toolset_override": "",
            "created_at": None,
            "updated_at": None,
            **overrides,
        }
        self._next_task_id += 1
        self._tasks.append(t)
        return t

    # -- DB interface --

    async def fetch(self, query: str, *args: Any) -> list[Row]:
        self.queries.append((query, args))
        q_upper = query.upper()

        if "KANBAN_BOARDS" in q_upper:
            return [Row(b) for b in self._boards]

        if "KANBAN_TASKS" in q_upper or "FROM KANBAN_" in q_upper:
            results = list(self._tasks)
            # Filter by board_id
            for i, arg in enumerate(args):
                idx = query.lower().find("$" + str(i + 1))
                if idx > 0:
                    col = query[:idx].strip().split()[-1].lower()
                    if col in ("board_id",):
                        results = [t for t in results if t.get("board_id") == arg]
            # Filter by sprint
            for i, arg in enumerate(args):
                marker = f"${i + 1}"
                before = query[:query.lower().find(marker)].strip()
                if "sprint" in before.lower() and arg:
                    results = [t for t in results if t.get("sprint") == arg]
            return [Row(r) for r in results]

        if "KANBAN_EVENTS" in q_upper:
            return [Row(e) for e in self._events]

        if "KANBAN_DEPENDENCIES" in q_upper:
            board_id_filters = set()
            for i, arg in enumerate(args):
                marker = f"${i + 1}"
                before = query[:query.lower().find(marker)].strip()
                if "depends_on_task_id" in before.lower():
                    board_id_filters.add(arg)
            if board_id_filters:
                results = [d for d in self._deps if d.get("task_id") in board_id_filters or d.get("depends_on_task_id") in board_id_filters]
            else:
                results = list(self._deps)
            return [Row(r) for r in results]

        if "NOTIFICATIONS" in q_upper:
            return []

        if "KANBAN_AGENT_LOG" in q_upper:
            return [Row(r) for r in self._logs]

        if "STREAM_EVENTS" in q_upper:
            return [Row(e) for e in self._events if e.get("event_type") != "task.created"]

        return []

    def _parse_insert_cols(self, query: str) -> list[str]:
        """Extract column names from an INSERT INTO ... (...) VALUES query."""
        # Find the parenthesized column list after tablename
        after_into = query.split("INTO", 1)[-1] if "INTO" in query else query
        paren_start = after_into.find("(")
        paren_end = after_into.find(")")
        if paren_start >= 0 and paren_end > paren_start:
            cols_str = after_into[paren_start + 1:paren_end]
            return [c.strip().lower().strip('"') for c in cols_str.split(",") if c.strip()]
        return []

    async def fetchrow(self, query: str, *args: Any) -> Row | None:
        self.queries.append((query, args))
        q_upper = query.upper()

        if "INSERT INTO KANBAN_BOARDS" in q_upper:
            cols = self._parse_insert_cols(query)
            board_kwargs = {}
            for i, col in enumerate(cols):
                if i < len(args):
                    val = args[i]
                    # JSON-string columns: parse back to dict/list for storage
                    if col in ("columns", "wip_limits", "config"):
                        if isinstance(val, str):
                            try:
                                val = json.loads(val)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    board_kwargs[col] = val
                    if col == "name":
                        board_kwargs["name"] = val
            b = self._add_board(**board_kwargs)
            return Row({"id": b["id"]})

        if "INSERT INTO KANBAN_TASKS" in q_upper:
            cols = self._parse_insert_cols(query)
            task_kwargs = {}
            for i, col in enumerate(cols):
                if i < len(args):
                    task_kwargs[col] = args[i]
            t = self._add_task(
                title=task_kwargs.get("title", "task"),
                description=task_kwargs.get("description", ""),
                column_name=task_kwargs.get("column_name", "backlog"),
                priority=task_kwargs.get("priority", "p2"),
                tags=task_kwargs.get("tags", ""),
                assigned_to=task_kwargs.get("assigned_to", ""),
                board_id=args[0] if args else "1",
                needs_review=bool(task_kwargs.get("needs_review", False)),
            )
            return Row({"id": t["id"]})

        if "UPDATE KANBAN_TASKS" in q_upper:
            # Find task by last arg (id)
            task_id = args[-1] if args else None
            if task_id:
                for t in self._tasks:
                    if t["id"] == task_id:
                        if "column_name" in query.lower():
                            for arg_idx, arg in enumerate(args):
                                col_marker = f"${arg_idx + 1}"
                                if f"column_name={col_marker}" in query.lower().replace(" ", "").replace("\n", ""):
                                    t["column_name"] = arg
                        if "claim_token" in query.lower() and "claim_token is null" in query.lower():
                            t["claim_token"] = "tok-" + task_id
                            t["column_name"] = "in_progress"
                        t["updated_at"] = "2026-01-01T00:00:00"
                        return Row({"id": task_id, "board_id": t.get("board_id", "1")})
            return Row({"id": task_id or "1", "board_id": "1"})

        # SELECT ... WHERE id = $1
        if "WHERE ID = $" in q_upper or "WHERE ID=$" in q_upper:
            lookup_id = args[0] if args else ""
            for t in self._tasks:
                if t["id"] == lookup_id:
                    return Row(t)
            for b in self._boards:
                if b["id"] == lookup_id:
                    return Row(b)

        if "SELECT CONFIG FROM" in q_upper:
            return Row({"config": json.dumps({"automations": []})})

        if "SELECT" in q_upper and "FROM KANBAN_TASKS" in q_upper:
            # Stats queries
            if "COUNT(*)" in q_upper:
                return Row({"count": len(self._tasks)})

            if "DISTINCT SPRINT" in q_upper:
                return []

            t = self._tasks[-1] if self._tasks else None
            return Row(t) if t else None

        return None

    async def fetchval(self, query: str, *args: Any) -> int | str:
        self.queries.append((query, args))
        q_upper = query.upper()
        if "COUNT(*)" in q_upper:
            if "AND COLUMN_NAME = 'done'" in q_upper:
                return sum(1 for t in self._tasks if t["column_name"] == "done")
            if "AND COLUMN_NAME = 'in_progress'" in q_upper:
                return sum(1 for t in self._tasks if t["column_name"] == "in_progress")
            if "AND FLAKY_TEST_NAME" in q_upper:
                return sum(1 for t in self._tasks if t.get("flaky_test_name"))
            return len(self._tasks)
        if "SELECT TAGS" in q_upper:
            t = next((t for t in self._tasks if t["id"] == args[0]), None)
            return t.get("tags", "") if t else ""
        return 0

    async def execute(self, query: str, *args: Any) -> str:
        self.queries.append((query, args))
        q_upper = query.upper()

        if "INSERT INTO KANBAN_EVENTS" in q_upper:
            self._events.append({
                "id": self._next_event_id,
                "board_id": args[0] if len(args) > 0 else "1",
                "task_id": args[1] if len(args) > 1 else "",
                "event_type": args[2] if len(args) > 2 else "unknown",
                "payload": args[3] if len(args) > 3 else "{}",
                "created_at": "2026-01-01T00:00:00",
            })
            self._next_event_id += 1

        elif "INSERT INTO KANBAN_AGENT_LOG" in q_upper:
            self._logs.append({
                "task_id": args[0],
                "agent_id": args[1],
                "action": args[2],
                "detail": args[3] if len(args) > 3 else "",
                "created_at": "2026-01-01T00:00:00",
            })

        elif "INSERT INTO KANBAN_DEPENDENCIES" in q_upper:
            self._deps.append({
                "task_id": args[0],
                "depends_on_task_id": args[1],
            })

        elif "DELETE FROM" in q_upper:
            pass  # no-op in memory

        elif "UPDATE KANBAN_TASKS" in q_upper:
            # Parse SET clauses
            task_id = args[-1]
            set_clause = query.split("SET")[1].split("WHERE")[0] if "SET" in query else ""
            for t in self._tasks:
                if t["id"] != task_id:
                    continue
                # Simple column=value parse for $N params
                import re as _re
                parts = _re.findall(r'(\w+)\s*=\s*\$(\d+)', set_clause)
                for col, idx_str in parts:
                    idx = int(idx_str) - 1
                    if idx < len(args):
                        t[col] = args[idx]
                t["updated_at"] = "2026-01-01T00:00:00"

        elif "INSERT INTO NOTIFICATIONS" in q_upper:
            pass

        return "OK"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kanban_db():
    """Fresh fake kanban DB with a pre-created board."""
    db = FakeKanbanDB()
    db._add_board(
        id="1",
        columns=json.dumps(["triage", "backlog", "ready", "in_progress", "review", "done", "blocked"]),
    )
    return db


@pytest.fixture
def make_request(kanban_db):
    """Factory for creating minimal FastAPI request stubs."""
    def _make():
        return SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(db=kanban_db)
            )
        )
    return _make


# ===================================================================
# TESTS
# ===================================================================


class TestRepoAnalysisPhase:
    """Phase 1: Analyze the remote repo and extract issues."""

    @pytest.mark.asyncio
    async def test_repo_analyzer_parses_github_url(self):
        """repo_analyzer correctly extracts owner/repo from various URL formats."""
        from harness.tools.repo_analyzer import RepoAnalyzerTool

        tool = RepoAnalyzerTool()
        owner, repo = tool._parse_github_url("https://github.com/Ganeshkumar-1508/bank_poc_agentic_ai")
        assert owner == "Ganeshkumar-1508"
        assert repo == "bank_poc_agentic_ai"

        owner, repo = tool._parse_github_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

        owner, repo = tool._parse_github_url("owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    @pytest.mark.asyncio
    async def test_repo_analyzer_rejects_invalid_url(self):
        from harness.tools.repo_analyzer import RepoAnalyzerTool
        tool = RepoAnalyzerTool()
        result = await tool.run(url="not-a-url")
        assert result.success is False
        assert "invalid_url" in (result.error or "")


class TestKanbanBoardLifecycle:
    """Phase 2: Kanban board creation and task management."""

    @pytest.mark.asyncio
    async def test_create_board_and_list(self, kanban_db, make_request):
        """Create a board, verify it appears in listing."""
        from api.routers.kanban import create_board, list_boards
        from api.routers.kanban import BoardCreate

        req = make_request()
        body = BoardCreate(name="E2E test board", description="End-to-end pipeline test")
        result = await create_board(req, body)
        assert result["status"] == "ok"
        assert "id" in result

        listing = await list_boards(req)
        assert len(listing["boards"]) >= 1
        assert any(b["name"] == "E2E test board" for b in listing["boards"])

    @pytest.mark.asyncio
    async def test_create_task_in_board(self, kanban_db, make_request):
        """Create tasks representing repo issues across columns."""
        from api.routers.kanban import create_task, list_tasks
        from api.routers.kanban import TaskCreate

        req = make_request()

        # Simulate issues found in bank_poc_agentic_ai repo
        issues = [
            ("Fix interest calculation overflow", "Interest calc returns negative for large values", "p1"),
            ("Add input validation for account creation", "Missing checks on account number format", "p2"),
            ("Improve test coverage on transaction module", "Transaction handler has < 60% coverage", "p2"),
        ]

        task_ids = []
        for title, desc, priority in issues:
            body = TaskCreate(board_id="1", title=title, description=desc, priority=priority)
            result = await create_task(req, board_id="1", body=body)
            assert result["status"] == "ok"
            task_ids.append(result["id"])

        # Verify all tasks listed
        listing = await list_tasks(req, board_id="1")
        assert len(listing["tasks"]) == 3

        # Check column defaults to backlog
        for t in listing["tasks"]:
            assert t["column"] == "backlog"

    @pytest.mark.asyncio
    async def test_task_lifecycle_column_transitions(self, kanban_db, make_request):
        """Task moves through columns: backlog → ready → in_progress → review → done."""
        from api.routers.kanban import create_task, update_task, claim_task, complete_task, get_task, TaskCreate, TaskUpdate

        req = make_request()
        body = TaskCreate(board_id="1", title="Fix login bug", description="Token validation fails", priority="p1")
        created = await create_task(req, board_id="1", body=body)
        task_id = created["id"]

        # backlog → ready
        await update_task(req, task_id, TaskUpdate(column_name="ready"))
        t = await get_task(req, task_id)
        assert t["task"]["column"] == "ready"

        # ready → in_progress (claim)
        claimed = await claim_task(req, task_id)
        assert claimed["status"] == "claimed"
        t = await get_task(req, task_id)
        assert t["task"]["column"] == "in_progress"

        # in_progress → done (complete, no review needed)
        await update_task(req, task_id, TaskUpdate(result_summary="Fixed null check in auth.py"))
        completed = await complete_task(req, task_id)
        assert completed["status"] == "ok"

        t = await get_task(req, task_id)
        assert t["task"]["column"] == "done"

    @pytest.mark.asyncio
    async def test_task_requires_review_goes_to_review_column(self, kanban_db, make_request):
        """Tasks with needs_review=True go to review column on complete."""
        from api.routers.kanban import create_task, claim_task, complete_task, get_task, review_task, TaskCreate, ReviewBody

        req = make_request()
        body = TaskCreate(board_id="1", title="Update API docs", description="Needs review", needs_review=True)
        created = await create_task(req, board_id="1", body=body)
        task_id = created["id"]

        await claim_task(req, task_id)
        completed = await complete_task(req, task_id)
        assert completed["target_column"] == "review"

        t = await get_task(req, task_id)
        assert t["task"]["column"] == "review"

        # Approve
        review_body = ReviewBody(action="approve", reviewer="ai_reviewer", notes="Looks good")
        result = await review_task(req, task_id, body=review_body)
        assert result["action"] == "approve"
        assert result["task"]["column"] == "done"

    @pytest.mark.asyncio
    async def test_rejected_task_goes_back_to_in_progress(self, kanban_db, make_request):
        """Rejected review sends task back to in_progress with notes."""
        from api.routers.kanban import create_task, claim_task, complete_task, get_task, review_task, TaskCreate, ReviewBody

        req = make_request()
        body = TaskCreate(board_id="1", title="Refactor db layer", description="Needs review", needs_review=True)
        created = await create_task(req, board_id="1", body=body)
        task_id = created["id"]

        await claim_task(req, task_id)
        await complete_task(req, task_id)

        # Reject
        review_body = ReviewBody(action="reject", reviewer="senior_dev", notes="Missing migration rollback")
        result = await review_task(req, task_id, body=review_body)
        assert result["action"] == "reject"
        assert result["task"]["column"] == "in_progress"
        assert result["task"]["reviewStatus"] == "rejected"

    @pytest.mark.asyncio
    async def test_block_and_unblock_task(self, kanban_db, make_request):
        """Block moves task to blocked column; unblock returns it to ready."""
        from api.routers.kanban import create_task, get_task, block_task, unblock_task, TaskCreate

        req = make_request()
        body = TaskCreate(board_id="1", title="Fix flaky test", description="Test times out intermittently")
        created = await create_task(req, board_id="1", body=body)
        task_id = created["id"]

        await block_task(req, task_id)
        t = await get_task(req, task_id)
        assert t["task"]["column"] == "blocked"
        assert t["task"]["failureCount"] == 1

        await unblock_task(req, task_id)
        t = await get_task(req, task_id)
        assert t["task"]["column"] == "ready"
        assert t["task"]["failureCount"] == 0


class TestAutoTriageFlow:
    """Phase 3: Auto-triage uses LLM to decompose a task into a plan."""

    @pytest.mark.asyncio
    async def test_triage_column_task_llm_decomposition(self, kanban_db, make_request, monkeypatch):
        """Auto-triage calls LLM, gets subtasks, moves task to backlog with plan."""
        from api.routers.kanban import create_task, triage_task, get_task, TaskCreate, TriageBody

        # Mock LLM to return a structured plan
        fake_plan = {
            "title": "Fix interest calculation overflow",
            "description": "Interest calc returns negative for large principle values due to integer overflow",
            "subtasks": [
                {"title": "Audit interest calculation", "description": "Review calc logic in ledger.py", "estimated_minutes": 20},
                {"title": "Add overflow guard", "description": "Wrap calc in try/catch with Decimal type", "estimated_minutes": 30},
                {"title": "Add unit test", "description": "Test edge cases: large values, zero, negative", "estimated_minutes": 15},
            ],
            "estimated_minutes": 65,
            "tags": ["finance", "bug", "overflow"],
        }

        async def fake_llm_chat(messages, **kwargs):
            return json.dumps(fake_plan)

        import harness.llm as llm_module
        monkeypatch.setattr(llm_module, "LLMClient", lambda: SimpleNamespace(chat=fake_llm_chat))

        req = make_request()
        body = TaskCreate(board_id="1", title="Fix interest calculation overflow",
                          description="Interest calc returns negative for large values", priority="p1",
                          column_name="triage")
        created = await create_task(req, board_id="1", body=body)
        task_id = created["id"]

        # Auto-triage
        triage_body = TriageBody(mode="auto")
        result = await triage_task(req, task_id, body=triage_body)

        assert result["mode"] == "auto"
        assert result["plan"] is not None
        assert len(result["plan"]["subtasks"]) == 3
        assert result["subtasks_created"] == 3

        # Task moved to backlog with refined title
        t = await get_task(req, task_id)
        assert t["task"]["column"] == "backlog"
        assert "overflow" in t["task"]["title"].lower()

    @pytest.mark.asyncio
    async def test_triage_fallback_on_llm_error(self, kanban_db, make_request, monkeypatch):
        """If LLM fails, triage returns mode=auto_fallback with the error."""
        from api.routers.kanban import create_task, triage_task, get_task, TaskCreate, TriageBody

        async def failing_chat(messages, **kwargs):
            raise RuntimeError("LLM unavailable")

        import harness.llm as llm_module
        monkeypatch.setattr(llm_module, "LLMClient", lambda: SimpleNamespace(chat=failing_chat))

        req = make_request()
        body = TaskCreate(board_id="1", title="Fix something", description="Something broke")
        created = await create_task(req, board_id="1", body=body)
        task_id = created["id"]

        result = await triage_task(req, task_id, body=TriageBody(mode="auto"))
        assert result["mode"] == "auto_fallback"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_manual_triage_returns_task_unchanged(self, kanban_db, make_request):
        """Manual triage returns the task as-is with no plan."""
        from api.routers.kanban import create_task, triage_task, TaskCreate, TriageBody

        req = make_request()
        body = TaskCreate(board_id="1", title="Manual task", description="Handle manually")
        created = await create_task(req, board_id="1", body=body)
        task_id = created["id"]

        result = await triage_task(req, task_id, body=TriageBody(mode="manual"))
        assert result["mode"] == "manual"
        assert result["plan"] is None


class TestOrchestratorDecomposition:
    """Phase 4: Orchestrator decomposes a goal into kanban tasks on a board."""

    @pytest.mark.asyncio
    async def test_orchestrate_creates_board_and_tasks(self, kanban_db):
        """Orchestrator tool creates a board with decomposed tasks."""
        from harness.memory.db_context import set_db

        # Set db via the new accessor (replaces Database._instance)
        set_db(kanban_db)

        from harness.tools.orchestrator_tool import cmd_orchestrate

        goal = "Fix test failures in the transaction module of bank_poc"
        result = await cmd_orchestrate(goal, repo_context="")

        data = json.loads(result)
        assert "board_id" in data
        assert data["status"] == "created"
        assert data["task_count"] >= 1

        # Verify tasks were created in kanban_tasks
        tasks = kanban_db._tasks
        assert len(tasks) >= data["task_count"]
        # First task should be ready (no parents)
        first_task = next((t for t in tasks if t["board_id"] == data["board_id"]), None)
        assert first_task is not None

    @pytest.mark.asyncio
    async def test_orchestrate_monitor_reports_status(self, kanban_db):
        """Monitor correctly reports board status based on task columns."""
        from harness.memory.db_context import set_db
        set_db(kanban_db)

        from harness.tools.orchestrator_tool import cmd_orchestrate, cmd_orchestrate_monitor

        # Create a board with tasks
        goal = "Fix bugs in auth module"
        result = await cmd_orchestrate(goal, repo_context="")
        data = json.loads(result)
        board_id = data["board_id"]

        # Initially — should show in_progress or ready
        status = await cmd_orchestrate_monitor(board_id)
        status_data = json.loads(status)
        assert status_data["board_id"] == board_id
        assert status_data["status"] in ("in_progress", "completed", "blocked")

        # Complete all tasks
        for t in kanban_db._tasks:
            if t["board_id"] == board_id:
                t["column_name"] = "done"

        status = await cmd_orchestrate_monitor(board_id)
        status_data = json.loads(status)
        assert status_data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_orchestrate_reports_blocked_tasks(self, kanban_db):
        """Monitor detects blocked/stalled tasks."""
        from harness.memory.db_context import set_db
        set_db(kanban_db)

        from harness.tools.orchestrator_tool import cmd_orchestrate, cmd_orchestrate_monitor

        goal = "Fix database connection pool"
        result = await cmd_orchestrate(goal, repo_context="")
        data = json.loads(result)
        board_id = data["board_id"]

        # Block a task with high failure count
        for t in kanban_db._tasks:
            if t["board_id"] == board_id:
                t["column_name"] = "blocked"
                t["failure_count"] = 3

        status = await cmd_orchestrate_monitor(board_id)
        status_data = json.loads(status)
        assert status_data["status"] in ("blocked", "stalled")


class TestKanbanStats:
    """Board statistics reflect the true state of tasks."""

    @pytest.mark.asyncio
    async def test_board_stats_counts_columns_correctly(self, kanban_db, make_request):
        """Stats endpoint returns accurate counts per column."""
        from api.routers.kanban import get_board_stats, create_task, TaskCreate

        req = make_request()

        # Create 5 tasks in different states
        states = ["backlog", "backlog", "in_progress", "done", "blocked"]
        for i, col in enumerate(states):
            body = TaskCreate(board_id="1", title=f"Task {i}", column_name=col)
            await create_task(req, board_id="1", body=body)

        stats = await get_board_stats(req, "1")
        assert stats["total"] == 5
        assert stats["done"] == 1
        assert stats["wip"] == 1


class TestAgentKanbanTools:
    """Agent-facing kanban tools (used by subagents to interact with board)."""

    @pytest.mark.asyncio
    async def test_kanban_list_shows_board_tasks(self, kanban_db):
        """kanban_list returns tasks from the first available board."""
        from harness.tools.kanban_agent_tools import cmd_kanban_list

        # Add tasks to the default board
        kanban_db._add_task(board_id="1", title="Agent task A", column_name="backlog")
        kanban_db._add_task(board_id="1", title="Agent task B", column_name="in_progress")

        result = await cmd_kanban_list()
        parsed = json.loads(result)
        assert parsed.get("error") is None
        # Note: this hits localhost:8001 — in real test would need httpx mock
        # This validates the tool compiles and constructs valid requests

    @pytest.mark.asyncio
    async def test_kanban_agent_tools_registered(self):
        """All kanban agent tools are properly registered in the tool registry."""
        from harness.tools.registry import registry

        kanban_tools = {"kanban_list", "kanban_show", "kanban_create", "kanban_assign",
                        "kanban_start", "kanban_complete", "kanban_block", "kanban_unblock",
                        "kanban_comment", "kanban_link", "kanban_heartbeat"}
        registered = set()
        for entry in registry.list_entries():
            if entry.name in kanban_tools:
                registered.add(entry.name)

        for tool in kanban_tools:
            assert tool in registered, f"{tool} not registered"


class TestKnowledgeGraphIntegration:
    """KG tool integration with exploration."""

    @pytest.mark.asyncio
    async def test_kg_tools_compiled_and_registered(self):
        """Knowledge graph tools register without errors."""
        from harness.tools.registry import registry

        kg_tools = {"kg_search", "kg_callers", "kg_callees", "kg_graph_status", "kg_refresh"}
        registered = set()
        for entry in registry.list_entries():
            if entry.name in kg_tools:
                registered.add(entry.name)

        for tool in kg_tools:
            assert tool in registered, f"{tool} not registered"

    @pytest.mark.asyncio
    async def test_kg_search_requires_query(self):
        """kg_search returns error when query is missing."""
        from harness.tools.knowledge_graph_tool import KGSearchTool
        tool = KGSearchTool()
        result = await tool.run()
        assert result.success is False
        assert "Query is required" in result.output

    @pytest.mark.asyncio
    async def test_kg_graph_status_reports_no_graph_when_uninitialized(self):
        """kg_graph_status returns 'no graph' when CodeGraph is not initialized."""
        from harness.tools.knowledge_graph_tool import KGGraphStatusTool
        tool = KGGraphStatusTool()
        result = await tool.run()
        assert result.success is False
        assert "No knowledge graph found" in result.output


class TestSelfHealing:
    """Self-healing tool availability."""

    @pytest.mark.asyncio
    async def test_attempt_heal_tool_registered(self):
        """attempt_heal is registered in the healing toolset."""
        from harness.tools.registry import registry
        entries = [e for e in registry.list_entries() if e.name == "attempt_heal"]
        assert len(entries) >= 1


class TestFullPipelineE2E:
    """The full end-to-end: repo → triage → board → dispatch → fix → review → done."""

    @pytest.mark.asyncio
    async def test_complete_repo_to_done_with_mocked_explore(self, kanban_db, make_request, monkeypatch):
        """Simulates a complete run: repo analyzed → tasks created → triaged → worked → reviewed → done.

        This is the core E2E scenario: a repo with issues flows through the
        entire agent pipeline without real LLM calls.
        """
        from api.routers.kanban import (
            BoardCreate, TaskCreate, TaskUpdate, TriageBody, ReviewBody,
            create_board, create_task, update_task, triage_task,
            claim_task, complete_task, review_task, block_task,
            list_tasks, get_board_stats,
        )

        # 1. Create a board
        req = make_request()
        board = await create_board(req, BoardCreate(
            name="bank_poc_agentic_ai — issues",
            description="Issues found in bank_poc_agentic_ai repo",
        ))
        board_id = board["id"]

        # 2. Seed issues (simulates what repo analysis would find)
        issues = [
            ("Interest calc overflow", "p1", "InterestCalc returns negative for large principle"),
            ("Missing input validation", "p2", "Account creation API lacks input validation"),
            ("Transaction test flaky", "p2", "test_transaction_rollback fails intermittently"),
            ("Config not loaded from env", "p1", "DATABASE_URL not read from environment"),
        ]

        task_ids = []
        for title, priority, desc in issues:
            body = TaskCreate(board_id=board_id, title=title, description=desc,
                              priority=priority, column_name="triage")
            created = await create_task(req, board_id=board_id, body=body)
            task_ids.append(created["id"])

        # 3. Auto-triage each issue (mock LLM)
        async def mock_chat(messages, **kwargs):
            return json.dumps({
                "title": messages[-1].content.split("Task title: ")[1].split("\n")[0] if hasattr(messages[-1], "content") else "fixed",
                "description": "Triage plan generated",
                "subtasks": [{"title": "Analyze", "description": "Root cause analysis", "estimated_minutes": 15}],
                "estimated_minutes": 30,
                "tags": ["auto-triaged"],
            })

        import harness.llm as llm_module
        monkeypatch.setattr(llm_module, "LLMClient", lambda: SimpleNamespace(chat=mock_chat))

        for tid in task_ids:
            await triage_task(req, tid, body=TriageBody(mode="auto"))

        # 4. Move triaged tasks to ready
        listing = await list_tasks(req, board_id=board_id)
        for t in listing["tasks"]:
            if t["column"] == "backlog":
                await update_task(req, t["id"], TaskUpdate(column_name="ready"))

        # 5. Simulate workers picking up and completing tasks
        completed_fixes = []
        for tid in task_ids[:2]:  # First 2 succeed
            await claim_task(req, tid)
            await update_task(req, tid, TaskUpdate(
                result_summary=f"Fixed: applied change to source files\nFiles changed: [src/module.py]",
            ))
            completed = await complete_task(req, tid)
            completed_fixes.append(completed)

        # 6. One task needs review
        task_under_review = task_ids[2]
        await claim_task(req, task_under_review)
        await update_task(req, task_under_review, TaskUpdate(
            needs_review=True,
            result_summary="Fixed flaky test — added retry logic",
        ))
        await complete_task(req, task_under_review)
        review_result = await review_task(req, task_under_review, body=ReviewBody(
            action="approve", reviewer="ai_reviewer", notes="Retry logic looks correct",
        ))
        assert review_result["task"]["column"] == "done"

        # 7. One task gets blocked
        await claim_task(req, task_ids[3])
        await block_task(req, task_ids[3])

        # 8. Verify final board state
        final = await list_tasks(req, board_id=board_id)
        columns = [t["column"] for t in final["tasks"]]

        assert columns.count("done") == 3  # 2 completed + 1 reviewed
        assert columns.count("blocked") == 1

        stats = await get_board_stats(req, board_id)
        assert stats["total"] == 4
        assert stats["done"] >= 3

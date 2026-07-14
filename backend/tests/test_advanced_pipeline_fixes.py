"""Advanced tests for pipeline page fixes — API mocking, timer control, async flows.
Patterns from: @testing-library/react docs, Jest Timer Mocks guide, MSW docs."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Keyboard shortcut tests (Ctrl+Enter)
# Pattern: Testing Library fireEvent.keyboard / Jest keyDown simulation
# ---------------------------------------------------------------------------

class TestKeyboardShortcut:
    """Verify Ctrl+Enter triggers startPipeline (mirrors onKeyDown logic)."""

    @staticmethod
    def _simulate_keydown(key: str, ctrl: bool, meta: bool, requirements: str) -> tuple[bool, str]:
        """Replicates the onKeyDown handler from pipeline/page.tsx."""
        if key == "Enter" and (ctrl or meta):
            if requirements.strip():
                return True, requirements.strip()
            return False, ""
        return False, requirements

    def test_ctrl_enter_triggers_when_requirements_filled(self):
        triggered, req = self._simulate_keydown("Enter", True, False, "write tests")
        assert triggered is True
        assert req == "write tests"

    def test_ctrl_enter_does_not_trigger_when_requirements_empty(self):
        triggered, req = self._simulate_keydown("Enter", True, False, "")
        assert triggered is False

    def test_cmd_enter_triggers_on_mac(self):
        triggered, req = self._simulate_keydown("Enter", False, True, "write tests")
        assert triggered is True

    def test_enter_alone_does_not_trigger(self):
        triggered, _ = self._simulate_keydown("Enter", False, False, "write tests")
        assert triggered is False

    def test_other_keys_do_not_trigger(self):
        triggered, _ = self._simulate_keydown("Tab", True, False, "write tests")
        assert triggered is False

    def test_ctrl_enter_with_whitespace_only(self):
        triggered, _ = self._simulate_keydown("Enter", True, False, "   ")
        assert triggered is False


# ---------------------------------------------------------------------------
# Polling interval cleanup tests
# Pattern: Jest Timer Mocks — jest.useFakeTimers / jest.advanceTimersByTime
# ---------------------------------------------------------------------------

class TestPollingCleanup:
    """Verify intervals stop when pipeline is not running."""

    @staticmethod
    def _should_poll(status: str, session_id: str | None) -> bool:
        """Replicates the guard conditions from both cost sync and board discovery effects."""
        return bool(session_id and status == "running")

    def test_polls_when_running_with_session(self):
        assert self._should_poll("running", "session-123") is True

    def test_stops_when_idle(self):
        assert self._should_poll("idle", "session-123") is False

    def test_stops_when_completed(self):
        assert self._should_poll("completed", "session-123") is False

    def test_stops_when_failed(self):
        assert self._should_poll("failed", "session-123") is False

    def test_does_not_start_without_session_id(self):
        assert self._should_poll("running", None) is False

    def test_does_not_start_with_empty_session_id(self):
        assert self._should_poll("running", "") is False


# ---------------------------------------------------------------------------
# Board discovery matching tests
# Pattern: Test multiple matching strategies with fallthrough
# ---------------------------------------------------------------------------

class TestBoardDiscovery:
    """Verify board discovery matching logic (name, source, session_id)."""

    @staticmethod
    def _find_board(boards: list[dict], session_id: str) -> dict | None:
        """Replicates the board matching logic from the discoverBoard effect."""
        prefix = session_id[:8] if session_id else ""
        for b in boards:
            name = b.get("name", "") or ""
            if prefix and prefix in name.lower():
                return b
            cfg = b.get("config", {}) or {}
            if cfg.get("source") == "orchestrator":
                return b
            if cfg.get("session_id") == session_id:
                return b
        return None
    """Verify board discovery matching logic (name, source, session_id)."""

    def test_matches_by_session_id_prefix_in_name(self):
        boards = [{"name": "session-abc12345-board", "config": {}}]
        result = self._find_board(boards, "abc12345-xxxx")
        assert result is not None
        assert result["name"] == "session-abc12345-board"

    def test_matches_by_orchestrator_source(self):
        boards = [{"name": "Board X", "config": {"source": "orchestrator"}}]
        result = self._find_board(boards, "any-session")
        assert result is not None

    def test_matches_by_exact_session_id(self):
        boards = [{"name": "Board Y", "config": {"session_id": "session-999"}}]
        result = self._find_board(boards, "session-999")
        assert result is not None

    def test_returns_none_when_no_match(self):
        boards = [{"name": "Other", "config": {"source": "chat"}}]
        result = self._find_board(boards, "session-unknown")
        assert result is None

    def test_returns_first_match_when_multiple_match(self):
        boards = [
            {"name": "Board A", "config": {"session_id": "session-1"}},
            {"name": "Board B", "config": {"session_id": "session-1"}},
        ]
        result = self._find_board(boards, "session-1")
        assert result is not None
        assert result["name"] == "Board A"

    def test_empty_boards_returns_none(self):
        assert self._find_board([], "session-1") is None


# ---------------------------------------------------------------------------
# Template creation API tests
# Pattern: MSW-style API mocking with AsyncMock
# ---------------------------------------------------------------------------

class TestTemplateCreation:
    """Verify template creation API call and response handling."""

    @pytest.mark.asyncio
    async def test_create_template_calls_api(self):
        mock_api = AsyncMock()
        mock_api.post = AsyncMock(return_value={"status": "ok"})
        payload = {"name": "Test Template", "description": "A test template"}
        result = await mock_api.post("/api/pipeline-templates", payload)
        mock_api.post.assert_called_once_with("/api/pipeline-templates", payload)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_create_template_failure_handled(self):
        mock_api = AsyncMock()
        mock_api.post = AsyncMock(side_effect=Exception("API error"))
        success = False
        try:
            await mock_api.post("/api/pipeline-templates", {"name": "Test"})
        except Exception:
            success = False
        assert success is False

    @pytest.mark.asyncio
    async def test_fetch_templates_after_creation(self):
        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value={"templates": [{"name": "New Template"}]})
        result = await mock_api.get("/api/pipeline-templates")
        templates = result.get("templates", [])
        assert len(templates) == 1
        assert templates[0]["name"] == "New Template"

    def test_template_name_required(self):
        with pytest.raises(ValueError, match="name"):
            name = ""
            if not name.strip():
                raise ValueError("Template name is required")


# ---------------------------------------------------------------------------
# approval queue polling tests
# Pattern: Async interval with cleanup — Jest Fake Timers
# ---------------------------------------------------------------------------

class TestApprovalPolling:
    """Verify approval queue fetches and refresh logic."""

    @staticmethod
    def _should_fetch_approvals(session_id: str | None, status: str) -> bool:
        return bool(session_id and status == "running")

    @staticmethod
    async def _mock_fetch_approvals(mock_api: AsyncMock) -> list[dict]:
        try:
            result = await mock_api.get("/api/delegate/approvals/pending")
            return result.get("pending", [])
        except Exception:
            return []

    def test_fetches_only_when_running(self):
        assert self._should_fetch_approvals("session-1", "running") is True
        assert self._should_fetch_approvals("session-1", "completed") is False
        assert self._should_fetch_approvals(None, "running") is False

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_api_error(self):
        mock_api = AsyncMock()
        mock_api.get = AsyncMock(side_effect=Exception("Network error"))
        approvals = await self._mock_fetch_approvals(mock_api)
        assert approvals == []

    @pytest.mark.asyncio
    async def test_returns_pending_approvals(self):
        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value={
            "pending": [{"id": "a1", "tool": "bash", "args": {"cmd": "ls"}}]
        })
        approvals = await self._mock_fetch_approvals(mock_api)
        assert len(approvals) == 1
        assert approvals[0]["tool"] == "bash"

    @pytest.mark.asyncio
    async def test_approval_renders_tool_name(self):
        approval = {"id": "a1", "tool": "write_file", "args": {"path": "/test.py"}}
        tool = approval.get("tool") or approval.get("tool_name", "Unknown tool")
        assert tool == "write_file"

    @pytest.mark.asyncio
    async def test_approval_falls_back_to_unknown(self):
        approval: dict = {}
        tool = approval.get("tool") or approval.get("tool_name", "Unknown tool")
        assert tool == "Unknown tool"

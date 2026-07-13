"""Tests for pipeline page fixes — adapter, branch/repo_url/mode passing."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Adapter tests (mirrors the logic in job-spec.ts)
# ---------------------------------------------------------------------------

def _to_job_spec(payload: dict) -> dict:
    """Replicates the toJobSpecFromPipelineQuickTest adapter logic."""
    test_config: dict = {}
    if payload.get("mode") is not None:
        test_config["mode"] = payload["mode"]
    if isinstance(payload.get("test_types"), list):
        test_config["test_types"] = payload["test_types"]
    if isinstance(payload.get("advanced_config"), dict):
        test_config.update(payload["advanced_config"])

    tier = max(1, min(3, payload.get("tier", 1)))

    return {
        "source": "pipeline-quick-test",
        "prompt": str(payload.get("requirements", payload.get("prompt", ""))),
        "repo_url": str(payload.get("repo_url", "")),
        "branch": str(payload.get("branch", "")) if payload.get("branch") else "main",
        "tier": tier,
        "capabilities": ["read_code", "write_test_files", "edit_existing_tests", "run_tests", "open_pr"],
        "approval": {"mode": "review_queue", "destination": "github_pr"},
        "context": {"source": "pipeline-quick-test"},
        "test_config": test_config,
    }


class TestAdapterBranchField:
    """Verify branch field flows correctly from pipeline page to backend."""

    def test_defaults_to_main_when_branch_not_provided(self):
        spec = _to_job_spec({"requirements": "test"})
        assert spec["branch"] == "main"

    def test_defaults_to_main_when_branch_empty(self):
        spec = _to_job_spec({"requirements": "test", "branch": ""})
        assert spec["branch"] == "main"

    def test_uses_provided_branch(self):
        spec = _to_job_spec({"requirements": "test", "branch": "develop"})
        assert spec["branch"] == "develop"

    def test_uses_master_branch(self):
        spec = _to_job_spec({"requirements": "test", "branch": "master"})
        assert spec["branch"] == "master"

    def test_uses_feature_branch(self):
        spec = _to_job_spec({"requirements": "test", "branch": "feature/new-feature"})
        assert spec["branch"] == "feature/new-feature"


class TestAdapterRepoUrlField:
    """Verify repo_url flows correctly from pipeline page to backend."""

    def test_defaults_to_empty_when_not_provided(self):
        spec = _to_job_spec({"requirements": "test"})
        assert spec["repo_url"] == ""

    def test_uses_provided_repo_url(self):
        spec = _to_job_spec({"requirements": "test", "repo_url": "https://github.com/foo/bar"})
        assert spec["repo_url"] == "https://github.com/foo/bar"

    def test_repo_url_passed_in_quick_test_mode(self):
        """Quick Test mode now passes repo_url to adapter."""
        spec = _to_job_spec({
            "requirements": "test",
            "repo_url": "https://github.com/octocat/Hello-World",
            "branch": "master",
        })
        assert spec["repo_url"] == "https://github.com/octocat/Hello-World"
        assert spec["branch"] == "master"


class TestAdapterModeField:
    """Verify mode (auto/ask/custom) flows through to test_config."""

    def test_mode_defaults_to_not_set_when_missing(self):
        spec = _to_job_spec({"requirements": "test"})
        assert "mode" not in spec["test_config"]

    def test_mode_auto_passed_through(self):
        spec = _to_job_spec({"requirements": "test", "mode": "auto"})
        assert spec["test_config"]["mode"] == "auto"

    def test_mode_ask_passed_through(self):
        spec = _to_job_spec({"requirements": "test", "mode": "ask"})
        assert spec["test_config"]["mode"] == "ask"

    def test_mode_custom_passed_through(self):
        spec = _to_job_spec({"requirements": "test", "mode": "custom"})
        assert spec["test_config"]["mode"] == "custom"


class TestAdapterAdvancedConfig:
    """Verify advanced config merges into test_config."""

    def test_advanced_config_timeout(self):
        spec = _to_job_spec({
            "requirements": "test",
            "advanced_config": {"timeout_seconds": 300},
        })
        assert spec["test_config"]["timeout_seconds"] == 300

    def test_advanced_config_max_retries(self):
        spec = _to_job_spec({
            "requirements": "test",
            "advanced_config": {"max_retries": 5},
        })
        assert spec["test_config"]["max_retries"] == 5

    def test_advanced_config_parallelism(self):
        spec = _to_job_spec({
            "requirements": "test",
            "advanced_config": {"parallelism": 4},
        })
        assert spec["test_config"]["parallelism"] == 4

    def test_advanced_config_multiple_fields(self):
        spec = _to_job_spec({
            "requirements": "test",
            "advanced_config": {
                "timeout_seconds": 600,
                "max_retries": 3,
                "parallelism": 2,
                "shard_count": 4,
                "os": "linux",
                "auto_commit": True,
            },
        })
        assert spec["test_config"]["timeout_seconds"] == 600
        assert spec["test_config"]["max_retries"] == 3
        assert spec["test_config"]["parallelism"] == 2
        assert spec["test_config"]["shard_count"] == 4
        assert spec["test_config"]["os"] == "linux"
        assert spec["test_config"]["auto_commit"] is True


class TestAdapterTierMapping:
    """Verify tier is set correctly for quick test vs orchestrate."""

    def test_quick_test_default_tier_1(self):
        spec = _to_job_spec({"requirements": "test"})
        assert spec["tier"] == 1

    def test_orchestrate_tier_2(self):
        spec = _to_job_spec({
            "requirements": "test",
            "repo_url": "https://github.com/foo/bar",
            "tier": 2,
        })
        assert spec["tier"] == 2

    def test_tier_capped_at_1_min(self):
        spec = _to_job_spec({"requirements": "test", "tier": 0})
        assert spec["tier"] == 1

    def test_tier_capped_at_3_max(self):
        spec = _to_job_spec({"requirements": "test", "tier": 5})
        assert spec["tier"] == 3


class TestHistoryFilter:
    """Verify history filter excludes subagent sessions."""

    def _filter_sessions(self, sessions: list[dict]) -> list[dict]:
        return [s for s in sessions if not (s.get("session_id") or "").startswith("subagent-")]

    def test_filters_out_subagent_sessions(self):
        raw = [
            {"session_id": "api-abc123", "goal": "test"},
            {"session_id": "subagent-sa-xyz", "goal": "explore"},
            {"session_id": "subagent-sa-abc", "goal": "analyze"},
            {"session_id": "api-def456", "goal": "test"},
        ]
        filtered = self._filter_sessions(raw)
        assert len(filtered) == 2
        assert all(not s["session_id"].startswith("subagent-") for s in filtered)

    def test_preserves_api_sessions(self):
        raw = [
            {"session_id": "api-abc123", "goal": "test"},
            {"session_id": "api-def456", "goal": "test"},
        ]
        filtered = self._filter_sessions(raw)
        assert len(filtered) == 2

    def test_handles_empty_list(self):
        assert self._filter_sessions([]) == []

    def test_handles_sessions_without_session_id(self):
        raw = [{"goal": "test"}, {"session_id": None}]
        filtered = self._filter_sessions(raw)
        assert len(filtered) == 2


class TestRunButtonValidation:
    """Verify Run button disabled logic matches the page code."""

    @staticmethod
    def _can_run(status: str, requirements: str, pipeline_mode: str, repo_url: str) -> bool:
        if status == "running":
            return True
        if not requirements.strip():
            return False
        if pipeline_mode == "orchestrate" and not repo_url.strip():
            return False
        return True

    def test_enabled_when_requirements_filled_quick_mode(self):
        assert self._can_run("idle", "write test", "quick", "")

    def test_disabled_when_requirements_empty(self):
        assert not self._can_run("idle", "", "quick", "")

    def test_disabled_when_orchestrate_mode_no_repo(self):
        assert not self._can_run("idle", "write test", "orchestrate", "")

    def test_enabled_when_orchestrate_mode_with_repo(self):
        assert self._can_run("idle", "write test", "orchestrate", "https://github.com/foo/bar")

    def test_enabled_when_running_always(self):
        assert self._can_run("running", "", "orchestrate", "")

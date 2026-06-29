"""Tests for :mod:`harness.testai_constants` and the 2-tier skill scan.

Mirrors hermes's pattern: bundled skills (shipped with repo) + user
skills (installed at runtime). Both are discoverable through the same
``skills_list`` tool but tagged with a ``source`` field.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


class TestTestaiConstants:
    def test_get_testai_home_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("TESTAI_HOME", raising=False)
        from harness.testai_constants import get_testai_home
        assert get_testai_home() == tmp_path / ".testai"

    def test_get_testai_home_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("TESTAI_HOME", str(tmp_path / "custom"))
        from harness.testai_constants import get_testai_home
        assert get_testai_home() == tmp_path / "custom"

    def test_get_testai_home_contextvar_override(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from harness.testai_constants import (
            get_testai_home,
            set_testai_home_override,
            reset_testai_home_override,
        )
        token = set_testai_home_override(tmp_path / "scoped")
        try:
            assert get_testai_home() == tmp_path / "scoped"
        finally:
            reset_testai_home_override(token)
        assert get_testai_home() == tmp_path / ".testai"

    def test_display_testai_home_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("TESTAI_HOME", raising=False)
        from harness.testai_constants import display_testai_home
        assert display_testai_home() == "~/.testai"

    def test_display_testai_home_custom(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # When TESTAI_HOME is under Path.home(), display uses ~/ shorthand
        # (mirrors hermes's display_hermes_home for the "default" profile).
        monkeypatch.setenv("TESTAI_HOME", str(tmp_path / "deploy"))
        from harness.testai_constants import display_testai_home
        assert display_testai_home() == "~/deploy"

    def test_display_testai_home_outside_home(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        # When TESTAI_HOME is NOT under Path.home() (e.g. Docker /opt/data),
        # display returns the absolute path verbatim.
        monkeypatch.setenv("TESTAI_HOME", str(tmp_path / "deploy"))
        from harness.testai_constants import display_testai_home
        assert display_testai_home() == str(tmp_path / "deploy")

    def test_get_skills_dir_under_testai_home(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("TESTAI_HOME", raising=False)
        from harness.testai_constants import get_skills_dir
        assert get_skills_dir() == tmp_path / ".testai" / "skills"

    def test_get_bundled_skills_dir_default(self, monkeypatch, tmp_path):
        from harness.testai_constants import get_bundled_skills_dir
        # When TESTAI_BUNDLED_SKILLS is unset, falls through to default arg.
        monkeypatch.delenv("TESTAI_BUNDLED_SKILLS", raising=False)
        default = tmp_path / "bundled"
        assert get_bundled_skills_dir(default=default) == default

    def test_get_bundled_skills_dir_env_override(self, monkeypatch, tmp_path):
        from harness.testai_constants import get_bundled_skills_dir
        monkeypatch.setenv("TESTAI_BUNDLED_SKILLS", str(tmp_path / "alt"))
        assert get_bundled_skills_dir(default=tmp_path / "default") == tmp_path / "alt"

    def test_get_tools_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from harness.testai_constants import get_tools_dir
        assert get_tools_dir() == tmp_path / ".testai" / "tools"

    def test_get_plugins_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from harness.testai_constants import get_plugins_dir
        assert get_plugins_dir() == tmp_path / ".testai" / "plugins"

    def test_is_container_false_on_host(self, monkeypatch):
        from harness.testai_constants import is_container
        monkeypatch.setattr(Path, "exists", lambda self: False)
        monkeypatch.setattr(Path, "read_text", lambda self: "", raising=False)
        is_container._cached = None  # reset cache
        assert is_container() is False
        is_container._cached = None  # clean up for next test

    def test_is_container_true_via_dockerenv(self, monkeypatch):
        from harness import testai_constants
        from harness.testai_constants import is_container
        monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/.dockerenv")
        is_container._cached = None
        assert is_container() is True
        is_container._cached = None
        testai_constants.is_container._cached = None


class TestSkillScanTwoTier:
    """Verify the bundled + user two-tier scan produces tagged results."""

    def test_bundled_skills_scanned_with_builtin_label(self, tmp_path, monkeypatch):
        # Build a fake bundled skill under tmp_path/.testai/skills
        bundled_root = tmp_path / "project" / ".testai" / "skills"
        skill = bundled_root / "demo-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: A demo skill.\n---\n# Demo\n",
            encoding="utf-8",
        )
        # User home points somewhere with no user skills
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "user-home")
        # Bundled skills default to <repo>/.testai/skills
        # We pass that exact path through by setting the env var
        monkeypatch.setenv("TESTAI_BUNDLED_SKILLS", str(bundled_root))
        monkeypatch.delenv("TESTAI_HOME", raising=False)
        from harness.tools.skill_tools import _scan_skills
        results = _scan_skills()
        names = {r["name"] for r in results}
        assert "demo-skill" in names
        # Find our skill and verify its source label
        demo = next(r for r in results if r["name"] == "demo-skill")
        assert demo["category"] == "builtin"

    def test_user_skills_override_bundled(self, tmp_path, monkeypatch):
        # Bundled has skill A
        bundled_root = tmp_path / "project" / ".testai" / "skills"
        (bundled_root / "shared-skill" / "SKILL.md").parent.mkdir(parents=True)
        (bundled_root / "shared-skill" / "SKILL.md").write_text(
            "---\nname: shared-skill\ndescription: Bundled version.\n---\n# Bundled\n",
            encoding="utf-8",
        )
        # User home has the same name with different content
        user_home = tmp_path / "user-home"
        user_skill = user_home / ".testai" / "skills" / "shared-skill"
        user_skill.mkdir(parents=True)
        (user_skill / "SKILL.md").write_text(
            "---\nname: shared-skill\ndescription: User override version.\n---\n# User\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", lambda: user_home)
        monkeypatch.setenv("TESTAI_BUNDLED_SKILLS", str(bundled_root))
        from harness.tools.skill_tools import _scan_skills
        results = _scan_skills()
        shared = [r for r in results if r["name"] == "shared-skill"]
        assert len(shared) == 1
        assert shared[0]["category"] == "user"  # user takes priority
        assert "User override" in shared[0]["description"]

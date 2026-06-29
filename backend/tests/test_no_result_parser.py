"""C6.1 v1.1 — the Greptile TREX pattern: NO result-parsing layer.

Per the research (https://www.greptile.com/trex, Momentic, Testim,
Codecov), agentic testing harnesses and test aggregators ingest
JUnit XML — but they don't write bespoke text parsers. Greptile
TREX runs tests in a sandbox; the agent reads the result natively.

TestAI's C6.1 v1.1 follows that pattern: the 4 bespoke parsers
(`PytestParser`, `VitestJsonParser`, `JestJsonParser`,
`LineOutputParser`) and the `parser_for()` dispatch have been
deleted. The orchestrator's test_executor / bash tool runs the
framework, the framework emits whatever its native flag produces
(`pytest --junit-xml=...`, `vitest --reporter=junit`, etc.), and the
agent reads the result file via `read_file`.

These tests assert:
  - the result-parsing module no longer exists
  - no code anywhere in `harness/` or `backend/` references the
    four deleted parser classes
  - the test-planner role body follows the Greptile TREX pattern
"""
from __future__ import annotations

import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# The result-parsing layer is GONE.
# ---------------------------------------------------------------------------


class TestNoResultParserModule:
    """`harness/tools/result_parsers.py` has been removed.

    Per the Greptile TREX pattern, TestAI doesn't parse test
    results. The agent runs the framework and reads whatever
    the framework emits.
    """

    def test_result_parsers_module_deleted(self):
        path = Path(__file__).resolve().parents[1] / "harness" / "tools" / "result_parsers.py"
        assert not path.exists(), f"result_parsers.py still exists at {path}"

    def test_cannot_import_deleted_module(self):
        with __import__("pytest").raises(ModuleNotFoundError):
            __import__("harness.tools.result_parsers")


class TestNoDeletedParserClassesAnywhere:
    """The 4 bespoke parsers must not be referenced anywhere in
    the production code (harness/) or the test code (backend/tests/).
    Regression guard: catches anyone reintroducing the deleted
    parsers."""

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _scan_for_legacy_references(self) -> list[str]:
        """Return a list of files that still reference any of the
        4 deleted parser classes by name."""
        root = self._repo_root()
        targets = (
            "PytestParser",
            "VitestJsonParser",
            "JestJsonParser",
            "LineOutputParser",
            "ParsedResult",       # the dataclass went with the parsers
            "parser_for",         # the dispatch function
        )
        offenders: list[str] = []
        for sub in ("harness", "tests", "api"):
            base = root / "backend" / sub
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                # Skip the no-result-parser test itself.
                if path.name == "test_no_result_parser.py":
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for tgt in targets:
                    if tgt in text:
                        offenders.append(f"{path}: {tgt}")
        return offenders

    def test_no_production_or_test_code_references_deleted_parsers(self):
        offenders = self._scan_for_legacy_references()
        assert not offenders, (
            "Deleted parsers are still referenced:\n  "
            + "\n  ".join(offenders)
        )


class TestPlannerRoleFollowsGreptilePattern:
    """The test-planner role body must follow the Greptile TREX
    pattern: no result-parsing layer, the framework string is
    free-form, the agent reads results natively."""

    def test_role_body_says_no_result_parsing(self):
        role_path = (
            Path(__file__).resolve().parents[2]
            / ".testai" / "prompts" / "agents" / "test-planner.txt"
        )
        body = role_path.read_text(encoding="utf-8")
        # The role body must say there's no result-parsing layer.
        assert "no result-parsing" in body.lower() or "no parsing" in body.lower(), (
            "test-planner role body must state there is no result-parsing layer "
            "(the Greptile TREX pattern)"
        )

    def test_role_body_references_greptile_trex(self):
        role_path = (
            Path(__file__).resolve().parents[2]
            / ".testai" / "prompts" / "agents" / "test-planner.txt"
        )
        body = role_path.read_text(encoding="utf-8")
        # The role body must name the convention it follows.
        assert "Greptile" in body or "TREX" in body, (
            "test-planner role body must name the convention it follows"
        )

    def test_role_body_lists_framework_invocation_flags(self):
        """The role body must teach the planner that each framework has
        a built-in CLI flag for emitting its native result format
        (JUnit XML, Playwright JSON, Allure, etc.) — the agent just
        invokes the right flag downstream."""
        role_path = (
            Path(__file__).resolve().parents[2]
            / ".testai" / "prompts" / "agents" / "test-planner.txt"
        )
        body = role_path.read_text(encoding="utf-8")
        # Spot-check 3 of the most common framework flags
        for flag in ("--junit-xml", "--reporter=junit", "playwright"):
            assert flag in body, (
                f"role body missing framework-invocation hint: {flag!r}"
            )

    def test_role_body_says_framework_string_is_free_form(self):
        role_path = (
            Path(__file__).resolve().parents[2]
            / ".testai" / "prompts" / "agents" / "test-planner.txt"
        )
        body = role_path.read_text(encoding="utf-8")
        assert "free-form" in body.lower()

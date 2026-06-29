"""Test Impact Analysis — selects only tests affected by code changes.

Tier 1 (file-level): uses git diff + import dependency graph to determine
which tests to run. Inspired by Tach (gauge.sh) and Datadog TIA.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_IMPORT_RE = re.compile(r"(?:from|import)\s+([\w.]+)")


def get_changed_files(repo_path: str, base_branch: str = "origin/main") -> list[str]:
    """Return list of changed files between current state and base branch."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_branch + "..."],
            capture_output=True, text=True, timeout=30, cwd=repo_path,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
        # Fallback: compare to HEAD
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=30, cwd=repo_path,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception as e:
        logger.warning("TIA: git diff failed: %s", e)
    return []


def _extract_imports(filepath: str) -> set[str]:
    """Extract module names imported by a Python file."""
    try:
        text = Path(filepath).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return set()
    imports: set[str] = set()
    for match in _IMPORT_RE.finditer(text):
        mod = match.group(1)
        parts = mod.split(".")
        if parts:
            imports.add(parts[0])
        if len(parts) > 1:
            imports.add(".".join(parts[:2]))
    return imports


def _resolve_module_to_file(module: str, repo_path: str, extension: str = ".py") -> str | None:
    """Resolve a module name to a file path in the repo."""
    as_path = module.replace(".", "/")
    candidates = [
        f"{as_path}{extension}",
        f"{as_path}/__init__{extension}",
        f"src/{as_path}{extension}",
        f"src/{as_path}/__init__{extension}",
        f"lib/{as_path}{extension}",
        f"app/{as_path}{extension}",
        f"packages/{as_path}{extension}",
        f"modules/{as_path}{extension}",
    ]
    for candidate in candidates:
        full = Path(repo_path) / candidate
        if full.exists():
            return str(full.relative_to(repo_path).as_posix())
    return None


def build_dependency_map(repo_path: str) -> dict[str, set[str]]:
    """Build map of test_file -> set of source files it depends on."""
    repo = Path(repo_path)
    test_patterns = [
        # Python
        "test_*.py", "*_test.py", "*_tests.py", "test_*.pyw",
        # JavaScript / TypeScript (also detect __tests__/ dir convention)
        "*.spec.js", "*.test.js", "*.spec.ts", "*.test.ts",
        "*.spec.jsx", "*.test.jsx", "*.spec.tsx", "*.test.tsx",
        "*.spec.mjs", "*.test.mjs", "*.spec.cjs", "*.test.cjs",
        "__tests__/*.js", "__tests__/*.ts", "__tests__/*.jsx", "__tests__/*.tsx",
        # Vue / Svelte component testing
        "*.spec.vue", "*.test.vue", "*.spec.svelte", "*.test.svelte",
        # Ruby
        "*_test.rb", "*_spec.rb",
        # PHP
        "*Test.php", "*_test.php",
        # Go
        "*_test.go",
        # Rust
        "*_test.rs", "*_test.rs",
        # Java / JVM
        "*Test.java", "Test*.java", "*Tests.java",
        "*_test.scala", "*Spec.scala", "*Test.scala",
        "*_test.kt", "*Test.kt",
        # Kotlin
        "*_test.kt", "*Test.kt",
        # Dart / Flutter
        "*_test.dart",
        # Swift
        "*Tests.swift", "*_test.swift",
        # C# / .NET
        "*Tests.cs", "*Test.cs",
        # Elixir
        "*_test.exs",
        # C / C++
        "*_test.cpp", "*_test.cc", "*Test.cpp", "*_test.cxx", "*_test.c", "*_test.h",
        # CUDA
        "*_test.cu", "*_test.cuh",
        # Clojure
        "*_test.clj",
        # Haskell
        "*Test.hs", "*Spec.hs",
        # R
        "test-*.R", "*_test.R",
        # Julia
        "*_test.jl",
        # Lua
        "*_test.lua", "*_spec.lua",
        # Erlang
        "*_test.erl", "*_SUITE.erl",
        # Shell
        "test_*.sh", "*_test.sh",
        # Perl
        "*.t",
        # Nim
        "*_test.nim",
        # Crystal
        "*_spec.cr",
        # BDD / Cucumber
        "*.feature",
        # SQL database tests
        "*_test.sql", "*_test.psql",
        # Protocol Buffers
        "*_test.proto",
        # CMake
        "*Test.cmake", "*_test.cmake",
        # Makefile
        "test_*.mk", "*.test.mk",
        # Zig
        "*_test.zig",
        # V / Vlang
        "*_test.v",
        # OCaml
        "*_test.ml", "*Test.ml",
        # PureScript
        "*Test.purs",
        # GraphQL
        "*.test.graphql", "*.spec.graphql",
    ]
    test_files = []
    for pattern in test_patterns:
        test_files.extend(repo.rglob(pattern))
    dep_map: dict[str, set[str]] = {}
    for tf in test_files:
        rel = tf.relative_to(repo).as_posix()
        imports = _extract_imports(str(tf))
        resolved: set[str] = set()
        for imp in imports:
            f = _resolve_module_to_file(imp, repo_path)
            if f:
                resolved.add(f)
        if resolved:
            dep_map[rel] = resolved
    return dep_map


def select_tests(
    changed_files: list[str],
    dep_map: dict[str, set[str]],
    all_test_files: list[str] | None = None,
) -> list[str]:
    """Select only test files affected by the changed files."""
    changed_set = set(changed_files)
    affected_tests: set[str] = set()
    for test_file, deps in dep_map.items():
        if deps & changed_set:
            affected_tests.add(test_file)
    # Always include tests that ARE the changed files
    test_suffixes = (
        "_test.py", "_tests.py", ".spec.js", ".test.js", ".spec.ts", ".test.ts",
        ".spec.jsx", ".test.jsx", ".spec.tsx", ".test.tsx",
        ".spec.mjs", ".test.mjs", ".spec.cjs", ".test.cjs",
        ".spec.vue", ".test.vue", ".spec.svelte", ".test.svelte",
        "_test.rb", "_spec.rb", "Test.php", "_test.php",
        "_test.go", "_test.rs",
        "Test.java", "Tests.java",
        "_test.scala", "Spec.scala", "Test.scala",
        "_test.kt", "Test.kt",
        "_test.dart", "Tests.swift", "_test.swift",
        "Tests.cs", "Test.cs",
        "_test.exs", "_test.cpp", "_test.cc", "Test.cpp", "_test.cxx",
        "_test.c", "_test.h", "_test.cu", "_test.cuh",
        "_test.clj", "Test.hs", "Spec.hs",
        "_test.R", "_test.jl", "_test.lua", "_spec.lua",
        "_test.erl", "_SUITE.erl", "_test.sh",
        ".t", "_test.nim", "_spec.cr",
        ".feature", "_test.sql", "_test.psql",
        "_test.proto", "Test.cmake", "_test.cmake",
        "_test.mk", ".test.mk",
        "_test.zig", "_test.v",
        "_test.ml", "Test.ml", "Test.purs",
        ".test.graphql", ".spec.graphql",
    )
    test_prefixes = ("test_", "__tests__")
    for cf in changed_files:
        if cf.endswith(test_suffixes) or any(cf.startswith(p) or ("/" + p) in cf for p in test_prefixes):
            affected_tests.add(cf)
    if not affected_tests and all_test_files:
        return all_test_files[:5]  # fallback: run a sample
    return sorted(affected_tests)


def compute_impact_summary(
    repo_path: str,
    base_branch: str = "origin/main",
) -> dict[str, Any]:
    """Full impact analysis: changed files → affected tests → skip list."""
    changed = get_changed_files(repo_path, base_branch)
    if not changed:
        return {"changed_files": [], "total_tests": 0, "skipped_tests": 0, "affected_tests": [], "impact_pct": 0}
    dep_map = build_dependency_map(repo_path)
    affected = select_tests(changed, dep_map)
    all_tests = list(dep_map.keys())
    total = len(all_tests)
    skipped = total - len(affected)
    return {
        "changed_files": changed,
        "total_tests": total,
        "skipped_tests": max(skipped, 0),
        "affected_tests": affected,
        "impact_pct": round(len(affected) / max(total, 1) * 100, 1),
    }

"""Repo analyzer — surfaces repo structure for the coordinator.

The orchestrator's coordinator calls this at job setup to understand
what kind of project it's working with. Returns:

  - file count by extension
  - detected languages (delegates to detect_languages tool's logic)
  - common entry points (main.py, index.js, cmd/*.go, app.py, …)
  - test directory structure
  - README / LICENSE presence
  - framework hints (Django, Flask, Express, Spring, Cargo, …)
    based on dependency manifests

The output is a markdown report the LLM can read directly, plus a
`data` dict for programmatic consumers.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry


# Common entry-point filenames. The first match wins.
_ENTRY_POINTS: list[str] = [
    "main.py", "app.py", "wsgi.py", "asgi.py", "manage.py", "server.py",
    "index.js", "index.ts", "server.js", "app.js", "main.js",
    "main.go", "main.rs", "src/main.rs", "src/main.go", "src/main.py",
    "cmd/main.go", "cmd/server/main.go",
    "Program.cs", "Startup.cs",
]

# Manifest filenames → framework hint. The key is the file path; the
# value is the framework string to surface.
_FRAMEWORK_MANIFESTS: list[tuple[str, str]] = [
    ("pyproject.toml", "Python (pyproject)"),
    ("setup.py", "Python (setuptools)"),
    ("requirements.txt", "Python (pip)"),
    ("Pipfile", "Python (Pipenv)"),
    ("poetry.lock", "Python (Poetry)"),
    ("package.json", "Node.js (npm)"),
    ("yarn.lock", "Node.js (Yarn)"),
    ("pnpm-lock.yaml", "Node.js (pnpm)"),
    ("Cargo.toml", "Rust (Cargo)"),
    ("go.mod", "Go (modules)"),
    ("pom.xml", "Java (Maven)"),
    ("build.gradle", "Java/Kotlin (Gradle)"),
    ("build.gradle.kts", "Kotlin (Gradle)"),
    ("Gemfile", "Ruby (Bundler)"),
    ("composer.json", "PHP (Composer)"),
    ("mix.exs", "Elixir (Mix)"),
    ("Project.toml", "Julia (Pkg)"),
    ("Package.swift", "Swift (SPM)"),
    ("pubspec.yaml", "Dart/Flutter (Pub)"),
    ("deno.json", "Deno"),
    ("bun.lockb", "Bun"),
    ("CMakeLists.txt", "C/C++ (CMake)"),
    ("Makefile", "Make-based build"),
]

# Framework hints based on package.json dependencies or requirements
# patterns. We just surface "found N deps" — deeper introspection
# isn't the tool's job.
_FW_HINTS_PACKAGE_JSON = {
    "react", "next", "vue", "svelte", "angular", "express", "fastify",
    "koa", "nestjs", "hono", "remix",
}
_FW_HINTS_REQUIREMENTS = {
    "django", "flask", "fastapi", "starlette", "aiohttp", "tornado",
    "bottle", "sanic", "falcon", "pyramid",
}

_SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", ".git", "venv", ".venv", "env", ".env",
    "__pycache__", "dist", "build", "target", ".next", ".nuxt",
    "vendor", "Pods", ".gradle", ".idea", ".vscode", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "coverage", ".coverage",
    ".terraform", "egg-info", ".eggs",
})


class RepoAnalyzerTool(BaseTool):
    name = "repo_analyzer"
    default_level = "allow"
    description = (
        "Analyse a repo's structure: file count by extension, detected "
        "languages, common entry points, test directories, README "
        "presence, and framework hints. Used by the orchestrator's "
        "coordinator during job setup to populate tech-stack metadata "
        "and to decide which test framework to invoke."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "/workspace/repo"},
                    "max_files": {"type": "integer", "default": 5000, "minimum": 100, "maximum": 100000},
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        repo_path = Path(kwargs.get("repo_path", "/workspace/repo"))
        if not repo_path.exists():
            return ToolResult(success=False, output=f"Path does not exist: {repo_path}", error="not_found")
        try:
            max_files = max(100, min(100_000, int(kwargs.get("max_files", 5_000) or 5_000)))
        except (TypeError, ValueError):
            max_files = 5_000

        ext_counts: Counter[str] = Counter()
        total_files = 0
        total_size = 0
        entry_points: list[str] = []
        manifests_found: list[str] = []
        frameworks: set[str] = set()
        has_readme = False
        has_license = False
        test_dirs: set[str] = set()
        skip_count = 0

        def _walk(p: Path, depth: int) -> None:
            nonlocal total_files, total_size, has_readme, has_license, skip_count
            if total_files >= max_files:
                return
            try:
                entries = list(p.iterdir())
            except (PermissionError, OSError):
                return
            for entry in entries:
                if total_files >= max_files:
                    return
                if entry.is_dir():
                    if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                        skip_count += 1
                        continue
                    # Heuristic: a dir named "tests" or "test" is a test dir.
                    if entry.name in ("tests", "test", "spec", "specs"):
                        test_dirs.add(str(entry.relative_to(repo_path)))
                    if depth < 8:
                        _walk(entry, depth + 1)
                elif entry.is_file():
                    total_files += 1
                    try:
                        total_size += entry.stat().st_size
                    except OSError:
                        pass
                    name = entry.name
                    ext = entry.suffix.lower()
                    if name in ("README.md", "README.rst", "README.txt", "README"):
                        has_readme = True
                    if name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
                        has_license = True
                    ext_counts[ext or "(no-ext)"] += 1
                    # Entry points: only at shallow depths (≤ 3).
                    if depth <= 3 and name in _ENTRY_POINTS:
                        rel = entry.relative_to(repo_path).as_posix()
                        entry_points.append(rel)
                    for manifest, fw in _FRAMEWORK_MANIFESTS:
                        if entry.name == manifest or (manifest in entry.name and depth <= 2):
                            manifests_found.append(manifest)
                            frameworks.add(fw)
                            break

        _walk(repo_path, 0)

        # Framework hints from package.json or requirements.
        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for name in deps:
                    short = name.split("/")[0].split("@")[0].lower()
                    if short in _FW_HINTS_PACKAGE_JSON:
                        frameworks.add(f"Node framework: {short}")
            except (json.JSONDecodeError, OSError):
                pass
        requirements = repo_path / "requirements.txt"
        if requirements.exists():
            try:
                text = requirements.read_text(encoding="utf-8", errors="ignore").lower()
                for fw in _FW_HINTS_REQUIREMENTS:
                    if fw in text:
                        frameworks.add(f"Python framework: {fw}")
            except OSError:
                pass

        # Build report.
        lines = [f"## Repo analysis: {repo_path}\n"]
        lines.append(f"- **Total files scanned**: {total_files:,} (skipped: {skip_count:,} dirs)")
        lines.append(f"- **Total size**: {total_size / 1024 / 1024:.2f} MB")
        lines.append(f"- **README**: {'yes' if has_readme else 'no'}")
        lines.append(f"- **LICENSE**: {'yes' if has_license else 'no'}")
        lines.append(f"- **Test directories**: {', '.join(sorted(test_dirs)) if test_dirs else 'none detected'}")
        if manifests_found:
            lines.append(f"- **Build manifests**: {', '.join(sorted(set(manifests_found)))}")
        if frameworks:
            lines.append(f"- **Framework hints**: {', '.join(sorted(frameworks))}")
        if entry_points:
            lines.append(f"\n### Entry points\n")
            for ep in sorted(entry_points)[:10]:
                lines.append(f"- `{ep}`")
        if ext_counts:
            lines.append(f"\n### Top file extensions\n")
            lines.append("| Extension | Count |")
            lines.append("|---|---:|")
            for ext, n in ext_counts.most_common(15):
                lines.append(f"| `{ext}` | {n:,} |")
        if not entry_points and not manifests_found:
            lines.append(
                "\n_No common entry points or build manifests detected. "
                "This may be a docs-only or config-only repository._"
            )
        return ToolResult(
            success=True, output="\n".join(lines),
            data={
                "total_files": total_files, "total_size": total_size,
                "extensions": dict(ext_counts.most_common(50)),
                "entry_points": entry_points,
                "manifests": sorted(set(manifests_found)),
                "frameworks": sorted(frameworks),
                "test_dirs": sorted(test_dirs),
                "has_readme": has_readme, "has_license": has_license,
            },
        )


registry.register(RepoAnalyzerTool(), toolset="read")

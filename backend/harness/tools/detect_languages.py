"""Language detection — cascading detection: enry → scc → pathlib fallback.

The `scc_lang_detector.py` tool wraps the function `detect_languages()`
defined here. The `tech_stack.py` tool also delegates to it.

Why cascading? `enry` (GitHub Linguist in Go) gives us 600+
languages with proper classification (vendored, generated,
documentation, prose). `scc` gives 200+ languages with line counts.
`pathlib` extension-counting is the always-available fallback.

The cascading pattern is the same one used by GitHub Linguist,
Sourcegraph, and Sentry. We prefer the most accurate tool that's
actually installed; we never fail just because the top tier is
missing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Vendored/generated/docs directory names. Files under these are not
# counted toward "user-written code". This list mirrors what GitHub
# Linguist uses; the Sentry version is shorter but covers the common
# cases. We don't try to be exhaustive — the cascading enry/scc tier
# handles vendored/generated more accurately.
_VENDORED_DIRS: frozenset[str] = frozenset({
    "node_modules", "vendor", "vendored", "third_party", "thirdparty",
    "bower_components", "jspm_packages", "Pods", "Carthage", "build",
    "dist", "out", "target", "_build", ".gradle", "venv", ".venv",
    "env", ".env", "site-packages", ".next", ".nuxt", ".svelte-kit",
})

# Common documentation/markdown extensions. enry and scc handle this
# better; this is the fallback only.
_DOC_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".mdx", ".rst", ".txt", ".adoc", ".org", ".wiki", ".textile",
})

# Common generated file extensions. Same caveat.
_GENERATED_EXTENSIONS: frozenset[str] = frozenset({
    ".min.js", ".min.css", ".lock", ".lockb", ".pyc", ".pyo", ".o",
    ".obj", ".class", ".jar", ".war", ".dll", ".so", ".dylib", ".exe",
    ".pdb", ".sum", ".mod",
})

# Extension → language for the pathlib fallback. We only cover the
# common 50ish languages — the enry/scc tiers cover 200-600.
_FALLBACK_LANGUAGES: dict[str, str] = {
    ".py": "Python", ".pyi": "Python", ".pyx": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sass": "Sass", ".less": "Less", ".vue": "Vue", ".svelte": "Svelte",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".c": "C", ".h": "C", ".hpp": "C++",
    ".swift": "Swift", ".m": "Objective-C", ".mm": "Objective-C++",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".ps1": "PowerShell", ".bat": "Batch", ".cmd": "Batch",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML", ".xml": "XML", ".csv": "CSV",
    ".sql": "SQL", ".graphql": "GraphQL", ".proto": "Protobuf",
    ".lua": "Lua", ".vim": "VimScript", ".el": "EmacsLisp",
    ".hs": "Haskell", ".ml": "OCaml", ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".clj": "Clojure", ".dart": "Dart",
    ".jl": "Julia", ".r": "R", ".pl": "Perl", ".tcl": "Tcl",
    ".groovy": "Groovy", ".f90": "Fortran", ".f95": "Fortran",
    ".pas": "Pascal", ".ada": "Ada", ".d": "D", ".nim": "Nim",
    ".zig": "Zig", ".v": "V", ".cr": "Crystal",
}


@dataclass
class LanguageDetection:
    """Result of a language detection pass.

    `languages` is a list of dicts with at least `name` and `bytes`
    (and optionally `percentage`, `files`). `source` indicates which
    tier produced the result (one of: "enry", "scc", "pathlib").
    `detected_files` is the total number of files scanned.
    """
    languages: list[dict[str, Any]] = field(default_factory=list)
    source: str = "pathlib"
    detected_files: int = 0
    error: str | None = None


def _is_vendored(path: Path, repo_root: Path) -> bool:
    try:
        rel = path.relative_to(repo_root).parts
    except ValueError:
        return False
    return any(part in _VENDORED_DIRS for part in rel)


def _run_sync(cmd: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    """Run a subprocess synchronously and return (rc, stdout, stderr)."""
    import subprocess
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return -1, "", str(exc)


async def _try_enry(repo_path: Path) -> LanguageDetection | None:
    """Try `enry` (GitHub Linguist in Go). Returns None if not installed."""
    if not shutil.which("enry"):
        return None
    rc, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_sync(["enry", str(repo_path)], timeout=60.0),
    )
    if rc != 0 or not stdout.strip():
        return None
    # enry output format: language<TAB>percentage per line.
    languages: list[dict[str, Any]] = []
    detected = 0
    for line in stdout.splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 2:
            continue
        try:
            pct = float(parts[1].rstrip("%"))
        except ValueError:
            continue
        languages.append({"name": parts[0], "percentage": pct})
        detected += 1
    if not languages:
        return None
    return LanguageDetection(languages=languages, source="enry", detected_files=detected)


async def _try_scc(repo_path: Path) -> LanguageDetection | None:
    """Try `scc` (Sloc Cloc and Code). Returns None if not installed."""
    if not shutil.which("scc"):
        return None
    rc, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_sync(
            ["scc", "--no-cocomo", "--format", "json", str(repo_path)],
            timeout=60.0,
        ),
    )
    if rc != 0 or not stdout.strip():
        return None
    import json as _json
    try:
        data = _json.loads(stdout)
    except _json.JSONDecodeError:
        return None
    languages: list[dict[str, Any]] = []
    total_lines = 0
    for entry in data if isinstance(data, list) else data.get("languages", []):
        name = entry.get("Name") or entry.get("name")
        lines = int(entry.get("Lines", entry.get("lines", 0)) or 0)
        if not name:
            continue
        languages.append({"name": name, "lines": lines})
        total_lines += lines
    for lang in languages:
        lang["percentage"] = (
            100.0 * lang["lines"] / total_lines if total_lines else 0.0
        )
    if not languages:
        return None
    return LanguageDetection(
        languages=languages, source="scc",
        detected_files=sum(
            int(entry.get("Count", entry.get("count", 0)) or 0)
            for entry in (data if isinstance(data, list) else data.get("languages", []))
        ),
    )


def _pathlib_fallback(repo_path: Path, max_files: int = 10_000) -> LanguageDetection:
    """Last-resort detection using only the standard library.

    Walks `repo_path`, skips vendored and generated directories, and
    counts files per language by extension. Returns a `LanguageDetection`
    with `source = "pathlib"`.
    """
    counts: Counter[str] = Counter()
    detected = 0
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if detected >= max_files:
            break
        if _is_vendored(path, repo_path):
            continue
        ext = path.suffix.lower()
        # Strip compound suffixes like .min.js
        if any(ext.endswith(g) for g in _GENERATED_EXTENSIONS):
            continue
        if ext in _DOC_EXTENSIONS:
            continue
        language = _FALLBACK_LANGUAGES.get(ext)
        if not language:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        counts[language] += size
        detected += 1
    total = sum(counts.values()) or 1
    languages = [
        {"name": name, "bytes": size, "percentage": 100.0 * size / total}
        for name, size in counts.most_common()
    ]
    return LanguageDetection(
        languages=languages, source="pathlib", detected_files=detected,
    )


async def detect_languages(path: str = ".") -> LanguageDetection:
    """Detect programming languages in a repository.

    Cascading order: enry → scc → pathlib. The first tier that
    returns a non-empty result wins. Always succeeds (pathlib is
    always available) but the most accurate tier installed is
    preferred.
    """
    repo_path = Path(path).expanduser().resolve()
    if not repo_path.exists():
        return LanguageDetection(
            languages=[], source="pathlib", detected_files=0,
            error=f"Path does not exist: {repo_path}",
        )
    if not repo_path.is_dir():
        return LanguageDetection(
            languages=[], source="pathlib", detected_files=0,
            error=f"Not a directory: {repo_path}",
        )
    for try_fn in (_try_enry, _try_scc):
        try:
            result = await try_fn(repo_path)
            if result and result.languages:
                return result
        except Exception as exc:
            logger.debug("Detection tier %s failed: %s", try_fn.__name__, exc)
    try:
        return _pathlib_fallback(repo_path)
    except Exception as exc:
        logger.warning("pathlib fallback failed: %s", exc)
        return LanguageDetection(
            languages=[], source="pathlib", detected_files=0,
            error=str(exc),
        )


def format_detection_for_prompt(detection: LanguageDetection) -> str:
    """Format a detection result as markdown for LLM consumption."""
    if not detection.languages:
        return (
            "No languages detected. The repository may be empty, "
            "or all files are vendored/generated."
        )
    lines = [
        f"## Language detection (source: {detection.source})\n",
        f"Scanned {detection.detected_files} file(s).\n",
        "| Language | Share |",
        "|---|---:|",
    ]
    for lang in detection.languages[:25]:
        share = lang.get("percentage", 0.0)
        lines.append(f"| {lang['name']} | {share:.1f}% |")
    if len(detection.languages) > 25:
        lines.append(
            f"\n_...and {len(detection.languages) - 25} more language(s) with <1% share._"
        )
    return "\n".join(lines)

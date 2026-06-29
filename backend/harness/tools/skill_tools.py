from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry


# ---------------------------------------------------------------------------
# Skill usage tracking — sidecar at ~/.testai/skills/.usage.json
# ---------------------------------------------------------------------------

_USAGE_FILE = Path.home() / ".testai" / "skills" / ".usage.json"

STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_ARCHIVED = "archived"


def _load_usage() -> dict[str, Any]:
    if _USAGE_FILE.exists():
        try:
            return json.loads(_USAGE_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save_usage(data: dict[str, Any]) -> None:
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _USAGE_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        tmp.replace(_USAGE_FILE)
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def track_skill_use(name: str, action: str = "use") -> None:
    """Bump usage counters for a skill. Action: 'use', 'view', or 'patch'."""
    try:
        data = _load_usage()
        record = data.setdefault(name, {"created_at": _now_iso(), "created_by": "agent", "pinned": False, "state": STATE_ACTIVE, "use_count": 0, "view_count": 0, "patch_count": 0})
        if action == "use":
            record["use_count"] = record.get("use_count", 0) + 1
            record["last_used_at"] = _now_iso()
        elif action == "view":
            record["view_count"] = record.get("view_count", 0) + 1
            record["last_viewed_at"] = _now_iso()
        elif action == "patch":
            record["patch_count"] = record.get("patch_count", 0) + 1
            record["last_patched_at"] = _now_iso()
        _save_usage(data)
    except Exception:
        pass


def _adapt_skill(content: str) -> str:
    replacements = [
        ("Bash", "bash"),
        ("Read", "read_file"),
        ("Edit", "bash"),
        ("Write", "bash"),
        ("Glob", "bash"),
        ("Grep", "bash"),
        ("WebFetch", "web_fetch"),
        ("WebSearch", "web_search"),
        ("Agent", "delegate_task"),
        ("`npx playwright test`", "use test_executor with framework=playwright"),
        ("`npm test`", "use test_executor"),
        ("`pytest`", "use test_executor with framework=pytest"),
        ("run `jest`", "use test_executor with framework=jest"),
        ("run `vitest`", "use test_executor with framework=vitest"),
    ]
    for old, new in replacements:
        content = content.replace(old, new)
    return content

from harness.testai_constants import (
    get_bundled_skills_dir as _get_bundled_skills_dir_impl,
)
from harness.testai_constants import get_skills_dir as _get_skills_dir_impl


def _get_skills_dir() -> Path:
    """Return the TestAI user-skills directory (default: ``~/.testai/skills/``).

    Resolves through :func:`harness.testai_constants.get_skills_dir` so
    that ``TESTAI_HOME`` overrides and ContextVar scoping work as
    expected. The directory is created on first read so user-installed
    skills land somewhere predictable.
    """
    user_dir = _get_skills_dir_impl()
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _get_bundled_skills_dir() -> Path:
    """Return the bundled-skills directory that ships with the TestAI repo.

    Resolves through :func:`harness.testai_constants.get_bundled_skills_dir`
    so that the ``TESTAI_BUNDLED_SKILLS`` env var can redirect packaged
    installs to an alternate path. Bundled skills are kept separate
    from the user's installed set so updates to one don't clobber
    the other.
    """
    # In the source checkout, bundled skills live at the project root
    # (one level up from ``harness/``). Packaged installs (pip wheel,
    # Docker image) override via the ``TESTAI_BUNDLED_SKILLS`` env var.
    default_path = Path(__file__).resolve().parent.parent.parent / ".testai" / "skills"
    return _get_bundled_skills_dir_impl(default=default_path)


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    meta: dict[str, Any] = {}
    rest = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                meta = yaml.safe_load(parts[1]) or {}
            except Exception:
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        k, _, v = line.partition(":")
                        meta[k.strip()] = v.strip().strip('"').strip("'")
            rest = parts[2]
    return meta, rest


_skills_cache: list[dict[str, Any]] | None = None
_skills_cache_ts: float = 0

def _scan_skills() -> list[dict[str, Any]]:
    global _skills_cache, _skills_cache_ts
    import time
    now = time.time()
    if _skills_cache is not None and (now - _skills_cache_ts) < 30:
        return _skills_cache

    user_dir = _get_skills_dir()
    bundled_dir = _get_bundled_skills_dir()
    results: list[dict[str, Any]] = []

    seen: set[str] = set()

    def _add_from_dir(base: Path, source_label: str = "user") -> None:
        if not base.exists():
            return
        for path in base.rglob("SKILL.md"):
            try:
                content = path.read_text("utf-8")
                meta, _ = _parse_frontmatter(content)
                name = meta.get("name", path.parent.name)
                if name in seen:
                    continue
                seen.add(name)
                md_meta = meta.get("metadata", {}) or {}
                results.append({
                    "name": name,
                    "description": meta.get("description", ""),
                    "version": meta.get("version", "1.0.0"),
                    "author": meta.get("author", ""),
                    "license": meta.get("license", ""),
                    "platforms": list(meta.get("platforms", []) or []),
                    "tags": list(meta.get("tags", []) or md_meta.get("tags", []) or []),
                    "category": meta.get("category") or md_meta.get("category", source_label),
                    "related_skills": list(md_meta.get("related_skills", []) or []),
                    "path": str(path.relative_to(base.parent)) if base != user_dir else f"user/{path.relative_to(user_dir)}",
                    "requires_toolsets": md_meta.get("requires_toolsets", []),
                    "config": md_meta.get("config", {}),
                })
            except Exception:
                pass

    # Scan user skills (takes priority)
    _add_from_dir(user_dir, "user")

    # Scan bundled skills shipped with the repo
    _add_from_dir(bundled_dir, "builtin")

    # Scan built-in skills from prompt library
    from harness.prompts import PROMPTS_DIR
    for path in sorted(PROMPTS_DIR.glob("skill-*.md")):
        try:
            content = path.read_text("utf-8").strip()
            name = path.stem.replace("skill-", "", 1)
            if name in seen:
                continue
            seen.add(name)
            first_line = content.split("\n")[0] if content else ""
            desc = first_line.lstrip("#").strip() if first_line.startswith("#") else name
            results.append({
                "name": name,
                "description": desc,
                "version": "1.0.0",
                "category": "builtin",
                "path": f"builtin/{path.name}",
                "requires_toolsets": [],
            })
        except Exception:
            pass

    _skills_cache = sorted(results, key=lambda s: s["name"])
    _skills_cache_ts = now
    return _skills_cache



def _load_skill(name: str) -> dict[str, Any] | None:
    search_dirs = [
        _get_skills_dir(),
        _get_bundled_skills_dir(),
    ]

    for base in search_dirs:
        if not base.exists():
            continue
        for path in base.rglob("SKILL.md"):
            try:
                content = path.read_text("utf-8")
                meta, body = _parse_frontmatter(content)
                skill_name = meta.get("name", path.parent.name)
                if skill_name == name:
                    return {
                        "name": skill_name,
                        "description": meta.get("description", ""),
                        "version": meta.get("version", "1.0.0"),
                        "author": meta.get("author", ""),
                        "content": body.strip(),
                        "requires_toolsets": meta.get("metadata", {}).get("requires_toolsets", []),
                        "tags": meta.get("metadata", {}).get("tags", []),
                    }
            except Exception:
                continue

    # Fallback: prompt library skill files
    from harness.prompts import PROMPTS_DIR
    for path in sorted(PROMPTS_DIR.glob("skill-*.md")):
        try:
            pname = path.stem.replace("skill-", "", 1)
            if pname == name:
                return {
                    "name": pname,
                    "description": "",
                    "version": "1.0.0",
                    "content": path.read_text("utf-8").strip(),
                    "requires_toolsets": [],
                    "tags": [],
                }
        except Exception:
            continue

    return None


class SkillsListTool(BaseTool):
    name = "skills_list"
    default_level = "allow"
    description = "List all available skills with their names and descriptions"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {},
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        skills = _scan_skills()
        if not skills:
            return ToolResult(
                success=True,
                output="No skills found.",
                data={"skills": []},
            )
        lines = ["## Available Skills\n"]
        for s in skills:
            lines.append(f"- **{s['name']}** v{s['version']} — {s['description']}")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"skills": skills},
        )


class SkillViewTool(BaseTool):
    default_level = "allow"
    name = "skill_view"
    description = "Load the full content of a skill by name"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The skill name to load",
                    },
                },
                "required": ["name"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        name = kwargs.get("name", "")
        if not name:
            return ToolResult(success=False, output="Provide a skill name", error="missing_name")

        skill = _load_skill(name)
        if not skill:
            return ToolResult(
                success=False,
                output=f"Skill '{name}' not found. Use skills_list to see available skills.",
                error="not_found",
            )

        track_skill_use(name, action="view")

        output = f"# {skill['name']} v{skill['version']}\n\n"
        if skill["description"]:
            output += f"{skill['description']}\n\n"
        if skill["requires_toolsets"]:
            output += f"Requires toolsets: {', '.join(skill['requires_toolsets'])}\n\n"
        output += skill["content"]

        return ToolResult(
            success=True,
            output=output,
            data=skill,
        )


class SkillManageTool(BaseTool):
    name = "skill_manage"
    description = "Create, edit, or delete skills"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "patch", "delete", "install"],
                        "description": "Action to perform. install: fetch from URL and save adapted.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill name",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full SKILL.md content (for create)",
                    },
                    "url": {
                        "type": "string",
                        "description": "URL to SKILL.md (for install action)",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Text to replace (for patch)",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text (for patch)",
                    },
                },
                "required": ["action", "name"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")
        content = kwargs.get("content", "")
        url = kwargs.get("url", "")
        old_string = kwargs.get("old_string", "")
        new_string = kwargs.get("new_string", "")

        skills_dir = _get_skills_dir()

        # Path-traversal guard: the user-supplied ``name`` must not escape
        # ``skills_dir`` (e.g. "../../etc/passwd").  We resolve the candidate
        # path and verify it stays inside the skills directory before doing
        # any I/O. (Phase-8 P0 #1)
        skill_path = (skills_dir / name / "SKILL.md").resolve()
        try:
            skills_dir_resolved = skills_dir.resolve()
        except Exception:
            skills_dir_resolved = skills_dir
        if not skills_dir_resolved.exists() or not skill_path.is_relative_to(skills_dir_resolved):
            return ToolResult(success=False, output="Invalid skill name (path traversal)", error="invalid_name")

        if action == "install":
            if not url:
                return ToolResult(success=False, output="URL required for install", error="missing_url")

            # SSRF guard — block fetches to private/internal IPs and cloud
            # metadata endpoints.  Runs before any network I/O. (Phase-8 P0 #1)
            try:
                from harness.tools.url_safety import is_safe_url
                if not is_safe_url(url):
                    return ToolResult(success=False, output="URL blocked by SSRF guard", error="ssrf_blocked")
            except Exception as e:
                return ToolResult(success=False, output=f"URL safety check failed: {e}", error="ssrf_check_error")

            try:
                import httpx
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(url, headers={"User-Agent": "TestAI/1.0"})
                    if resp.status_code != 200:
                        return ToolResult(success=False, output=f"Fetch failed: HTTP {resp.status_code}", error="fetch_failed")
                    raw = resp.text
            except Exception as e:
                return ToolResult(success=False, output=f"Fetch failed: {e}", error=str(e))

            adapted = _adapt_skill(raw)
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(adapted, "utf-8")

            # Post-install security scan — every community-sourced skill must
            # pass the static-analysis guard before it is considered
            # installed.  If the scan blocks, roll back the write so we never
            # leave a partially-installed skill on disk. (Phase-8 P0 #1)
            try:
                from harness.tools.skills_guard import scan_skill, should_allow_install
                scan_result = scan_skill(skill_path, source="community")
                allowed, reason = should_allow_install(scan_result)
                if not allowed:
                    try:
                        skill_path.unlink()
                    except OSError:
                        pass
                    return ToolResult(success=False, output=f"Scan failed: {reason}", error="scan_blocked")
            except Exception as e:
                # Scanner failure should not silently install an unscanned skill.
                try:
                    skill_path.unlink()
                except OSError:
                    pass
                return ToolResult(success=False, output=f"Scan failed: {e}", error="scan_error")

            track_skill_use(name, action="use")
            return ToolResult(success=True, output=f"Skill '{name}' installed from {url}")

        if action == "create":
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(content, "utf-8")
            track_skill_use(name, action="use")
            return ToolResult(success=True, output=f"Skill '{name}' created at {skill_path}")

        elif action == "patch":
            if not skill_path.exists():
                return ToolResult(success=False, output=f"Skill '{name}' not found", error="not_found")
            current = skill_path.read_text("utf-8")
            if old_string not in current:
                return ToolResult(success=False, output="old_string not found in skill", error="not_found")
            updated = current.replace(old_string, new_string)
            skill_path.write_text(updated, "utf-8")
            track_skill_use(name, action="patch")
            return ToolResult(success=True, output=f"Skill '{name}' patched")

        elif action == "delete":
            if skill_path.exists():
                skill_path.unlink()
                try:
                    skill_path.parent.rmdir()
                except OSError:
                    pass
            return ToolResult(success=True, output=f"Skill '{name}' deleted")

        return ToolResult(success=False, output=f"Unknown action: {action}", error="bad_action")


registry.register(SkillsListTool(), toolset="read")
registry.register(SkillViewTool(), toolset="read")
registry.register(SkillManageTool(), toolset="read")

"""Version Tracker — git-based version history per skill.

Each skill gets a versions.jsonl sidecar that records:
  - version number
  - timestamp
  - content hash
  - change summary
  - source (agent_evolution, user_edit, imported)

On skill edit, the old version is archived and the new version is recorded.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _skill_meta_dir(skill_name: str) -> Path:
    from harness.testai_constants import get_testai_home
    return get_testai_home() / "skills" / skill_name / ".evo"


def _versions_file(skill_name: str) -> Path:
    return _skill_meta_dir(skill_name) / "versions.jsonl"


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


class VersionTracker:
    """Git-based version history per skill."""

    def record_version(
        self,
        skill_name: str,
        content: str,
        source: str = "user_edit",
        summary: str = "",
    ) -> int:
        """Record a new version. Returns the version number."""
        versions = _read_jsonl(_versions_file(skill_name))
        version_num = len(versions) + 1
        content_hash = _content_hash(content)

        # Skip if content unchanged
        if versions and versions[-1].get("hash") == content_hash:
            return version_num - 1

        entry = {
            "version": version_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hash": content_hash,
            "source": source,
            "summary": summary[:200],
            "lines": len(content.splitlines()),
        }

        try:
            _append_jsonl(_versions_file(skill_name), entry)
        except Exception as e:
            logger.debug("VersionTracker.record_version failed for %s: %s", skill_name, e)

        return version_num

    def get_versions(self, skill_name: str) -> list[dict[str, Any]]:
        """Get all versions for a skill."""
        return _read_jsonl(_versions_file(skill_name))

    def get_latest(self, skill_name: str) -> dict[str, Any] | None:
        """Get the latest version record."""
        versions = self.get_versions(skill_name)
        return versions[-1] if versions else None

    def get_version_count(self, skill_name: str) -> int:
        """Get total number of versions."""
        return len(self.get_versions(skill_name))


# Global singleton
_tracker = VersionTracker()


def get_version_tracker() -> VersionTracker:
    return _tracker

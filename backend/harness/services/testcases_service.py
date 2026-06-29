"""Test cases service — CRUD for test cases, folders, flaky tests."""

from __future__ import annotations

import json
from typing import Any

from harness.memory.database import Database


class TestCasesService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def list_test_cases(self, project_id: str = "default-project",
                              test_type: str | None = None, status: str | None = None) -> list[dict]:
        query = "SELECT * FROM test_cases WHERE project_id = $1"
        params: list[Any] = [project_id]
        idx = 2
        if test_type:
            query += f" AND test_type = ${idx}"; params.append(test_type); idx += 1
        if status:
            query += f" AND status = ${idx}"; params.append(status); idx += 1
        query += " ORDER BY created_at DESC"
        rows = await self.db.fetch(query, *params)
        return [
            {"id": r["id"], "name": r["name"], "test_type": r["test_type"],
             "status": r["status"], "priority": r["priority"],
             "description": r["description"], "code": r["code"],
             "code_language": r["code_language"], "duration_ms": r["duration_ms"],
             "error_message": r["error_message"], "created_at": r["created_at"]}
            for r in rows
        ]

    async def get_test_case(self, test_case_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM test_cases WHERE id = $1", test_case_id)
        if not row:
            return None
        return {
            "id": row["id"], "name": row["name"], "description": row["description"],
            "test_type": row["test_type"], "status": row["status"], "priority": row["priority"],
            "steps": json.loads(row["steps"]) if row["steps"] else None,
            "expected": row["expected_result"],
            "test_data": json.loads(row["test_data"]) if row["test_data"] else None,
            "code": row["code"], "code_language": row["code_language"],
            "duration_ms": row["duration_ms"], "error_message": row["error_message"],
            "created_at": row["created_at"],
        }

    async def create_test_case(self, req: dict) -> dict:
        row = await self.db.fetchrow(
            "INSERT INTO test_cases (project_id, requirement_id, name, description, test_type, "
            "status, priority, steps, expected_result, test_data, code, code_language) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING *",
            req.get("project_id", "default-project"), req.get("requirement_id"),
            req["name"], req.get("description"), req.get("test_type", "api"),
            req.get("status", "pending"), req.get("priority", "medium"),
            json.dumps(req["steps"]) if req.get("steps") else None,
            req.get("expected"), json.dumps(req["test_data"]) if req.get("test_data") else None,
            req.get("code"), req.get("code_language", "python"),
        )
        return {"id": row["id"], "name": row["name"], "test_type": row["test_type"],
                "status": row["status"], "priority": row["priority"],
                "code": row["code"], "code_language": row["code_language"], "created_at": row["created_at"]}

    async def update_test_case(self, test_case_id: str, req: dict) -> dict | None:
        sets = []
        vals: list[Any] = []
        i = 1
        fields = [("name", "name"), ("description", "description"), ("test_type", "test_type"),
                  ("status", "status"), ("priority", "priority"), ("code", "code"),
                  ("code_language", "code_language"), ("duration_ms", "duration_ms"),
                  ("error_message", "error_message")]
        for field, col in fields:
            val = req.get(field)
            if val is not None:
                sets.append(f"{col}=${i}"); vals.append(val); i += 1
        for field, col in [("steps", "steps"), ("expected", "expected_result"), ("test_data", "test_data")]:
            val = req.get(field)
            if val is not None:
                sets.append(f"{col}=${i}"); vals.append(json.dumps(val) if isinstance(val, (dict, list)) else val); i += 1
        if not sets:
            return None
        sets.append("updated_at = NOW()")
        vals.append(test_case_id)
        row = await self.db.fetchrow(f"UPDATE test_cases SET {', '.join(sets)} WHERE id=${i} RETURNING id, name, test_type, status, updated_at", *vals)
        return dict(row) if row else None

    async def delete_test_case(self, test_case_id: str) -> None:
        await self.db.execute("DELETE FROM test_cases WHERE id = $1", test_case_id)

    async def get_flaky_tests(self, limit: int = 20) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT test_name, branch, total_runs, pass_count, fail_count, flaky_score, "
            "is_quarantined, last_healed, updated_at FROM flaky_tests "
            "ORDER BY flaky_score DESC, updated_at DESC LIMIT $1", limit,
        )
        return [{"testName": r["test_name"], "branch": r["branch"],
                  "totalRuns": r["total_runs"], "passCount": r["pass_count"],
                  "failCount": r["fail_count"], "flakyScore": round(r["flaky_score"], 2),
                  "isQuarantined": r["is_quarantined"], "lastHealed": r["last_healed"],
                  "updatedAt": r["updated_at"].isoformat() if r["updated_at"] else ""}
                for r in rows]

    async def toggle_quarantine(self, test_name: str, branch: str, is_quarantined: bool) -> None:
        await self.db.execute(
            "UPDATE flaky_tests SET is_quarantined=$1, updated_at=NOW() WHERE test_name=$2 AND branch=$3",
            is_quarantined, test_name, branch,
        )
        await self.db.execute(
            "UPDATE test_results SET is_quarantined=$1 WHERE test_name=$2 AND branch=$3",
            is_quarantined, test_name, branch,
        )

    async def list_folders(self) -> list[dict]:
        rows = await self.db.fetch("SELECT * FROM test_case_folders ORDER BY sort_order, name")
        return [dict(r) for r in rows]

    async def create_folder(self, name: str, filter_types: list[str], icon: str) -> dict:
        row = await self.db.fetchrow(
            "INSERT INTO test_case_folders (name, filter_types, icon) VALUES ($1, $2, $3) RETURNING *",
            name, filter_types, icon,
        )
        return dict(row)

    async def delete_folder(self, folder_id: str) -> None:
        await self.db.execute("DELETE FROM test_case_folders WHERE id = $1", folder_id)

    async def update_tags(self, test_case_id: str, tags: list[str]) -> None:
        await self.db.execute("UPDATE test_cases SET tags=$1, updated_at=NOW() WHERE id=$2", tags, test_case_id)

    async def link_artifact(self, test_case_id: str, artifact_id: str) -> None:
        """Link a test case to a pipeline artifact (test output, log, screenshot)."""
        await self.db.execute(
            "UPDATE test_cases SET artifact_id=$1, updated_at=NOW() WHERE id=$2",
            artifact_id, test_case_id,
        )

    async def get_linked_artifacts(self, test_case_id: str) -> list[dict]:
        """Return artifacts linked to a test case."""
        from harness.services.artifact_store import ArtifactStore
        store = ArtifactStore(self.db)
        artifacts = await store.list_by_entity("test_case", test_case_id)
        return [{"id": a["id"], "path": a["path"], "mime": a["mime_type"],
                 "description": a["description"], "created_at": a["created_at"]}
                for a in artifacts]

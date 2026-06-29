"""Tests for the C2.1 TestPlan HTTP surface.

The TestPlan artifact (harness/test_plan.py) is exposed via
`backend/api/routers/test_plans.py`. The store is wired as a
process-local `InMemoryTestPlanStore` on `app.state.test_plan_store`
by the lifespan in `api/main.py`.

These tests assert:
  - POST /api/test-plans creates a plan and returns its intent_hash
  - GET /api/test-plans/{id} returns the saved plan
  - GET /api/test-plans?intent_hash=... does the cache lookup
  - GET /api/test-plans?spec_id=... lists for a spec
  - Two plans with the same intent hash collapse to one (cache key)
  - GET /api/test-plans/prompt returns the role body
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.test_plan import InMemoryTestPlanStore, new_invariant_id, new_plan_id


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_store():
    """A FastAPI app with the test_plans router registered and a fresh
    in-memory store. We do NOT include the full TestAI app (which
    requires Postgres / Docker / real LLM); the router is isolated
    and only needs `app.state.test_plan_store` to function.
    """
    app = FastAPI()
    app.state.test_plan_store = InMemoryTestPlanStore()
    from api.routers.test_plans import router
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_store):
    return TestClient(app_with_store)


# ---------------------------------------------------------------------------
# POST /api/test-plans
# ---------------------------------------------------------------------------


class TestCreateTestPlan:
    def test_create_minimal_plan_returns_intent_hash(self, client):
        body = {
            "repo_url": "https://github.com/foo/bar",
            "repo_sha": "abc123",
            "framework": "pytest",
        }
        r = client.post("/api/test-plans", json=body)
        assert r.status_code == 200, r.text
        plan = r.json()["plan"]
        assert plan["plan_id"]
        assert plan["framework"] == "pytest"
        assert plan["repo_url"] == body["repo_url"]
        assert plan["intent_hash"]
        assert len(plan["intent_hash"]) == 64  # SHA-256 hex

    def test_create_plan_with_invariants(self, client):
        body = {
            "repo_url": "https://x/y",
            "repo_sha": "deadbeef",
            "framework": "playwright",
            "invariants": [
                {"description": "Login rejects expired cards", "target": "checkout.py:42"},
                {"description": "Empty cart is not allowed to checkout", "target": "cart.py:7"},
            ],
            "files": ["src/checkout.py", "src/cart.py"],
            "risk": "high",
            "requires_browser": True,
        }
        r = client.post("/api/test-plans", json=body)
        assert r.status_code == 200
        plan = r.json()["plan"]
        assert len(plan["invariants"]) == 2
        assert all(i["id"] for i in plan["invariants"])
        assert plan["files"] == ["src/checkout.py", "src/cart.py"]
        assert plan["risk"] == "high"
        assert plan["requires_browser"] is True

    def test_create_plan_with_explicit_ids_is_idempotent(self, client):
        pid = new_plan_id()
        iid = new_invariant_id()
        body = {
            "plan_id": pid,
            "repo_url": "https://a/b",
            "repo_sha": "f00d",
            "framework": "vitest",
            "invariants": [{"id": iid, "description": "x", "target": "x.ts:1"}],
        }
        r1 = client.post("/api/test-plans", json=body)
        assert r1.status_code == 200
        r2 = client.post("/api/test-plans", json=body)
        assert r2.status_code == 200
        assert r1.json()["plan"]["plan_id"] == r2.json()["plan"]["plan_id"] == pid

    def test_create_plan_with_bad_risk_falls_back_to_medium(self, client):
        body = {
            "repo_url": "https://a/b",
            "repo_sha": "f00d",
            "framework": "pytest",
            "risk": "INVALID",
        }
        r = client.post("/api/test-plans", json=body)
        # The plan is accepted; bad risk is silently normalized.
        assert r.status_code == 200
        assert r.json()["plan"]["risk"] == "medium"

    def test_create_plan_with_bad_category_falls_back_to_happy_path(self, client):
        body = {
            "repo_url": "https://a/b",
            "repo_sha": "f00d",
            "framework": "pytest",
            "invariants": [{"description": "x", "target": "x.py:1", "category": "NOPE"}],
        }
        r = client.post("/api/test-plans", json=body)
        assert r.status_code == 200
        assert r.json()["plan"]["invariants"][0]["category"] == "happy-path"

    def test_create_plan_rejects_invalid_body(self, client):
        r = client.post("/api/test-plans", json={"framework": "pytest"})  # no repo_url
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/test-plans/{id}
# ---------------------------------------------------------------------------


class TestGetTestPlanById:
    def test_get_existing_plan(self, client):
        body = {"repo_url": "https://a/b", "repo_sha": "1", "framework": "pytest"}
        created = client.post("/api/test-plans", json=body).json()["plan"]
        r = client.get(f"/api/test-plans/{created['plan_id']}")
        assert r.status_code == 200
        assert r.json()["plan"]["plan_id"] == created["plan_id"]

    def test_get_missing_plan_returns_404(self, client):
        r = client.get(f"/api/test-plans/{new_plan_id()}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/test-plans?intent_hash=...&spec_id=...  (cache + list)
# ---------------------------------------------------------------------------


class TestIntentHashCacheLookup:
    def test_cache_hit_returns_same_plan(self, client):
        body = {"repo_url": "https://a/b", "repo_sha": "abc", "framework": "pytest"}
        created = client.post("/api/test-plans", json=body).json()["plan"]
        intent = created["intent_hash"]
        r = client.get("/api/test-plans", params={"intent_hash": intent})
        assert r.status_code == 200
        assert r.json()["plan"]["plan_id"] == created["plan_id"]
        assert r.json()["match"] == "intent_hash"

    def test_cache_miss_returns_404(self, client):
        r = client.get("/api/test-plans", params={"intent_hash": "0" * 64})
        assert r.status_code == 404

    def test_identical_intent_collapses_to_one(self, client):
        """Two POSTs with the same (repo, sha, framework, files,
        invariants, requires_browser) MUST hash to the same
        intent_hash and resolve to the same plan via the cache.
        """
        body1 = {
            "plan_id": new_plan_id(),
            "repo_url": "https://a/b",
            "repo_sha": "abc",
            "framework": "pytest",
            "invariants": [
                {"id": "inv-1", "description": "x", "target": "x.py:1"},
            ],
        }
        body2 = dict(body1)
        body2["plan_id"] = new_plan_id()  # different plan_id
        c1 = client.post("/api/test-plans", json=body1).json()["plan"]
        c2 = client.post("/api/test-plans", json=body2).json()["plan"]
        # Same intent_hash (the cache key) ...
        assert c1["intent_hash"] == c2["intent_hash"]
        # ... different plan_ids (the planner can override) ...
        assert c1["plan_id"] != c2["plan_id"]
        # ... but cache lookup returns the most recent save.
        r = client.get("/api/test-plans", params={"intent_hash": c1["intent_hash"]})
        assert r.json()["plan"]["plan_id"] == c2["plan_id"]


class TestListForSpec:
    def test_list_returns_only_matching_spec(self, client):
        for spec in ("spec-A", "spec-A", "spec-B"):
            client.post("/api/test-plans", json={
                "spec_id": spec,
                "repo_url": f"https://a/{spec}",
                "repo_sha": "1",
                "framework": "pytest",
            })
        r = client.get("/api/test-plans", params={"spec_id": "spec-A"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert all(p["spec_id"] == "spec-A" for p in body["plans"])


# ---------------------------------------------------------------------------
# GET /api/test-plans/prompt
# ---------------------------------------------------------------------------


class TestPlannerPromptRoute:
    def test_returns_role_body(self, client):
        r = client.get("/api/test-plans/prompt")
        assert r.status_code == 200
        body = r.json()
        assert "prompt" in body
        assert "chars" in body
        # The role body must mention the test-planner identity.
        assert "planner" in body["prompt"].lower() or "TestPlan" in body["prompt"]


# ---------------------------------------------------------------------------
# 503 path — store not initialized
# ---------------------------------------------------------------------------


class TestStoreNotInitialized:
    def test_post_returns_503_when_store_missing(self):
        app = FastAPI()
        from api.routers.test_plans import router
        app.include_router(router)
        c = TestClient(app)
        r = c.post("/api/test-plans", json={
            "repo_url": "https://a/b", "repo_sha": "1", "framework": "pytest"
        })
        assert r.status_code == 503
        assert "TestPlan store not initialized" in r.json()["error"]

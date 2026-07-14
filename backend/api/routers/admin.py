import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..deps import get_db, get_agent
from .. import state
from harness.context import manager as scope_manager
from harness.memory import db_context

router = APIRouter(prefix="/api", tags=["admin"])


class CronJobCreate(BaseModel):
    name: str
    prompt: str
    schedule_type: str
    schedule_expr: str
    skill: str | None = None
    max_repeats: int | None = None
    repo_url: str = ""
    branch: str = ""


class CIRunRequest(BaseModel):
    repo_url: str
    pr_number: int = 0
    commit_sha: str = ""
    platform: str = ""
    token: str = ""
    api_key: str = ""


class WebhookPayload(BaseModel):
    event: str = ""
    payload: dict[str, Any] = {}


class SkillCreate(BaseModel):
    content: str


@router.get("/cron-jobs")
async def list_cron_jobs(request: Request):
    from harness.scheduler import store as cron_store
    db = get_db(request)
    jobs = await cron_store.list_jobs(db)
    return {"jobs": jobs}


@router.post("/cron-jobs")
async def create_cron_job(request: Request, req: CronJobCreate):
    from harness.scheduler import store as cron_store
    from harness.scheduler.jobs import parse_schedule
    db = get_db(request)
    next_run = parse_schedule(req.schedule_type, req.schedule_expr)
    job = await cron_store.create_job(db, {
        "name": req.name,
        "prompt": req.prompt,
        "schedule_type": req.schedule_type,
        "schedule_expr": req.schedule_expr,
        "skill": req.skill,
        "max_repeats": req.max_repeats,
        "repo_url": req.repo_url,
        "branch": req.branch,
        "next_run_at": next_run,
    })
    return {"job": job}


@router.patch("/cron-jobs/{job_id}")
async def update_cron_job(request: Request, job_id: str, req: dict[str, Any]):
    from harness.scheduler import store as cron_store
    db = get_db(request)
    ok = await cron_store.update_job(db, job_id, req)
    if not ok:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Job not found or no changes"})
    job = await cron_store.get_job(db, job_id)
    return {"job": job}


@router.delete("/cron-jobs/{job_id}")
async def delete_cron_job(request: Request, job_id: str):
    from harness.scheduler import store as cron_store
    db = get_db(request)
    ok = await cron_store.delete_job(db, job_id)
    if not ok:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return {"status": "ok"}


@router.post("/cron-jobs/{job_id}/run")
async def run_cron_job_now(request: Request, job_id: str):
    from harness.scheduler import store as cron_store
    db = get_db(request)
    job = await cron_store.get_job(db, job_id)
    if not job:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    await cron_store.update_job(db, job_id, {"next_run_at": datetime.now(timezone.utc), "state": "scheduled"})
    return {"status": "triggered", "job_id": job_id}


@router.get("/skills")
async def list_skills(request: Request):
    from harness.tools.skill_tools import _scan_skills
    try:
        loop = asyncio.get_event_loop()
        skills = await asyncio.wait_for(
            loop.run_in_executor(None, _scan_skills),
            timeout=5.0,
        )
        return {"skills": skills}
    except asyncio.TimeoutError:
        return {"skills": [], "error": "timeout"}
    except Exception as e:
        return {"skills": [], "error": str(e)}


@router.get("/skills/hub")
async def hub_skills(limit: int = 20, sort: str = "stars", search: str = ""):
    """Proxy to SkillsMP marketplace — 1.96M+ curated agent skills."""
    import httpx
    params = {"limit": min(limit, 50), "sortBy": sort}
    if search:
        params["search"] = search
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("https://skillsmp.com/api/skills", params=params)
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    # Fallback to top hardcoded skills if SkillsMP is unreachable
    return {"skills": [
        {"name": "docx", "description": "Create and edit Word documents", "author": "anthropics", "stars": 154456, "githubUrl": "https://github.com/anthropics/skills/tree/main/skills/docx"},
        {"name": "pdf", "description": "Extract text and tables from PDFs", "author": "anthropics", "stars": 154456, "githubUrl": "https://github.com/anthropics/skills/tree/main/skills/pdf"},
        {"name": "pptx", "description": "Create slide decks", "author": "anthropics", "stars": 154456, "githubUrl": "https://github.com/anthropics/skills/tree/main/skills/pptx"},
        {"name": "xlsx", "description": "Generate Excel spreadsheets", "author": "anthropics", "stars": 154456, "githubUrl": "https://github.com/anthropics/skills/tree/main/skills/xlsx"},
        {"name": "brainstorming", "description": "Creative brainstorming and ideation", "author": "obra/superpowers", "stars": 237100, "githubUrl": "https://github.com/obra/superpowers"},
    ], "pagination": {"total": 5, "totalAll": 5, "page": 1, "limit": 5, "hasNext": False},
       "filters": {"search": search, "sortBy": sort}, "fallback": True}


@router.post("/skills/import")
async def import_skills(request: Request, body: dict):
    """Import skills from a URL pointing to a skills directory or single skill.

    Body: {"url": "https://...", "category": "favorites"}
    """
    import json, httpx
    url = body.get("url", "")
    category = body.get("category", "imported")
    if not url:
        return JSONResponse(status_code=400, content={"error": "URL is required"})

    from harness.tools.skill_tools import _get_skills_dir
    skills_dir = _get_skills_dir()
    imported = []

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.get(url)
            resp.raise_for_status()
            data = resp.text

            # Try parsing as JSON (directory listing or bundle)
            try:
                bundle = json.loads(data)
                if isinstance(bundle, dict):
                    bundle = [bundle]
                for item in bundle:
                    name = item.get("name", "").strip().lower().replace(" ", "-")
                    content = item.get("content", item.get("body", ""))
                    if name and content:
                        skill_path = skills_dir / name / "SKILL.md"
                        skill_path.parent.mkdir(parents=True, exist_ok=True)
                        skill_path.write_text(content, "utf-8")
                        imported.append(name)
            except json.JSONDecodeError:
                # Single SKILL.md content
                import hashlib
                name = body.get("name", hashlib.md5(url.encode()).hexdigest()[:12])
                skill_path = skills_dir / name / "SKILL.md"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(data, "utf-8")
                imported.append(name)

        return {"status": "ok", "imported": imported, "count": len(imported)}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.get("/skills/curator-status")
async def skills_curator_status(request: Request):
    """Alias for /api/ops/skills/curator-status accessible under /api/skills/."""
    from .ops import get_curator_status
    return await get_curator_status(request)


@router.get("/skills/categories")
async def list_skill_categories(request: Request):
    db = get_db(request)
    rows = await db.fetch("SELECT DISTINCT category FROM skills ORDER BY category")
    return {"categories": [r["category"] for r in rows] if rows else []}


@router.patch("/skills/{name}/category")
async def update_skill_category(request: Request, name: str, body: dict):
    db = get_db(request)
    category = body.get("category", "uncategorized")
    await db.execute("INSERT INTO skills (name, content, category) VALUES ($1, '', $2) "
                     "ON CONFLICT (name) DO UPDATE SET category = $2", name, category)
    return {"status": "ok"}


@router.get("/skills/{name}")
async def get_skill(request: Request, name: str):
    from harness.tools.skill_tools import _load_skill
    skill = _load_skill(name)
    if not skill:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": f"Skill '{name}' not found"})
    return {"skill": skill}


@router.post("/skills/{name}")
async def create_or_update_skill(request: Request, name: str, req: SkillCreate):
    from harness.tools.skill_tools import _get_skills_dir
    db = db_context.get_db()

    skill_path = _get_skills_dir() / name / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)

    # Versioning: save current content as historic version before overwrite
    if skill_path.exists() and db:
        old_content = skill_path.read_text("utf-8")
        await db.execute(
            "INSERT INTO prompt_versions (name, content, version, status) "
            "VALUES ($1, $2, (SELECT COALESCE(MAX(version), 0) + 1 FROM prompt_versions WHERE name = $3), 'archived')",
            name, old_content, name,
        )

    skill_path.write_text(req.content, "utf-8")
    return {"status": "ok", "name": name}


@router.get("/skills/{name}/versions")
async def get_skill_versions(request: Request, name: str):
    db = db_context.get_db()
    if not db:
        return {"versions": []}
    rows = await db.fetch(
        "SELECT id, name, version, status, created_at FROM prompt_versions WHERE name = $1 ORDER BY version DESC",
        name,
    )
    return {
        "versions": [
            {
                "id": r["id"],
                "name": r["name"],
                "version": r["version"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


@router.post("/skills/{name}/revert/{version}")
async def revert_skill(request: Request, name: str, version: int):
    from harness.tools.skill_tools import _get_skills_dir
    db = db_context.get_db()
    if not db:
        return JSONResponse(status_code=503, content={"error": "Database not available"})

    row = await db.fetchrow(
        "SELECT content FROM prompt_versions WHERE name = $1 AND version = $2",
        name, version,
    )
    if not row:
        return JSONResponse(status_code=404, content={"error": f"Version {version} not found"})

    skill_path = _get_skills_dir() / name / "SKILL.md"
    old_content = skill_path.read_text("utf-8") if skill_path.exists() else ""
    await db.execute(
        "INSERT INTO prompt_versions (name, content, version, status) "
        "VALUES ($1, $2, (SELECT COALESCE(MAX(version), 0) + 1 FROM prompt_versions WHERE name = $3), 'archived')",
        name, old_content, name,
    )
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(row["content"], "utf-8")
    return {"status": "ok", "name": name, "version": version}


@router.delete("/skills/{name}")
async def delete_skill(request: Request, name: str):
    from harness.tools.skill_tools import _get_skills_dir
    import shutil
    skill_path = _get_skills_dir() / name
    if not skill_path.exists():
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": f"Skill '{name}' not found"})
    shutil.rmtree(skill_path)
    return {"status": "deleted", "name": name}


@router.post("/ci/run")
async def ci_run(request: Request, req: CIRunRequest):
    from harness.ci.git_providers import get_provider_from_url, get_provider

    db = get_db(request)
    agent = get_agent(request)

    if req.api_key:
        row = await db.fetchrow("SELECT id FROM api_keys WHERE key_value = $1 AND enabled = true", req.api_key)
        if not row:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"error": "Invalid API key"})
    else:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "API key required"})

    detected = get_provider_from_url(req.repo_url)
    if not detected:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"error": "Could not detect git platform from URL"})

    provider_name, repo_path, _ = detected
    if req.platform:
        provider_name = req.platform

    try:
        provider = get_provider(provider_name)
    except ValueError:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"error": f"Unsupported platform: {provider_name}"})

    token = req.token or os.environ.get(f"{provider_name.upper()}_TOKEN", "")

    try:
        diff = await provider.get_pr_diff(repo_path, req.pr_number, token)
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"error": f"Failed to fetch PR diff: {e}"})

    if not diff:
        return {"status": "skipped", "message": "No diff to analyze", "repo": repo_path, "pr": req.pr_number}

    _EXT_MAP = {
        ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
        ".jsx": "javascript", ".go": "go", ".rs": "rust", ".rb": "ruby",
        ".java": "java", ".kt": "kotlin", ".swift": "swift", ".cpp": "cpp",
        ".c": "c", ".h": "c", ".cs": "csharp", ".php": "php",
        ".vue": "vue", ".svelte": "svelte", ".css": "css", ".scss": "scss",
    }
    diff_extensions = set(re.findall(r'\.(\w+)', diff))
    language = "python"
    for diff_ext in diff_extensions:
        lang = _EXT_MAP.get("." + diff_ext)
        if lang:
            language = lang
            break

    framework = "auto"

    if not agent:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": "Agent not initialized"})

    run_id = str(uuid.uuid4())
    if agent:
        async def _ci_trace_handler(event_type: str, data: dict) -> None:
            await state.trace_handler(event_type, data, db)
        agent.trace_callback = _ci_trace_handler

    try:
        prompt = (
            f"Review this PR diff and generate tests for the changes:\n\n"
            f"```diff\n{diff[:8000]}\n```\n\n"
            f"Language: {language}\nFramework: {framework}\n\n"
            f"1. Analyze the changes and identify test scenarios\n"
            f"2. Generate test code using test_executor\n"
            f"3. Execute the tests and report results\n"
            f"4. Use delegate_task for parallel research if needed"
        )
        async with scope_manager.scope(
            run_id=run_id,
            labels={"pipeline_step": "ci_pipeline"},
        ):
            response = await agent.run(prompt)
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"error": f"Pipeline failed: {e}"})

    comment_body = f"## TestAI Results\n\n{response[:3000]}"

    try:
        if token:
            await provider.post_pr_comment(repo_path, req.pr_number, token, comment_body[:6000])
    except Exception:
        pass

    await db.execute(
        "INSERT INTO pipeline_runs (id, status, inputs, artifacts, state) VALUES ($1, $2, $3, $4, $5)",
        run_id, "completed",
        json.dumps({"repo": repo_path, "pr": req.pr_number, "platform": provider_name}),
        json.dumps([]), json.dumps({"response": response[:1000]}),
    )

    return {
        "run_id": run_id,
        "repo": repo_path,
        "pr": req.pr_number,
        "status": "completed",
        "has_tests": bool(response),
        "summary": response[:300] if response else "",
    }


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    requirements: str = ""
    mode: str = "auto"
    language: str = ""
    framework: str = ""
    tags: str = ""
    schedule: str = ""
    repo_url: str = ""


@router.get("/pipeline-templates")
async def list_templates(request: Request):
    db = get_db(request)
    rows = await db.fetch("SELECT * FROM pipeline_templates ORDER BY created_at DESC")
    return {"templates": [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r["description"] or "",
            "requirements": r["requirements"],
            "mode": r["mode"] or "auto",
            "language": r["language"] or "",
            "framework": r["framework"] or "",
            "tags": r["tags"] or "",
            "schedule": r["schedule"] or "",
            "repo_url": r["repo_url"] or "",
            "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
        }
        for r in rows
    ]}


@router.post("/pipeline-templates")
async def create_template(request: Request, req: TemplateCreate):
    db = get_db(request)
    row = await db.fetchrow(
        "INSERT INTO pipeline_templates (name, description, requirements, mode, language, framework, tags, schedule, repo_url) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
        req.name, req.description, req.requirements, req.mode, req.language, req.framework,
        req.tags, req.schedule, req.repo_url,
    )
    return {"id": row["id"]}


@router.patch("/pipeline-templates/{template_id}")
async def update_template(request: Request, template_id: str, req: dict[str, str]):
    db = get_db(request)
    allowed = {"name", "description", "requirements", "mode", "language", "framework", "tags", "schedule", "repo_url"}
    sets = []
    vals = []
    for k, v in req.items():
        if k in allowed:
            sets.append(f"{k} = ${len(vals) + 1}")
            vals.append(v)
    if sets:
        vals.append(template_id)
        await db.execute(
            f"UPDATE pipeline_templates SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${len(vals)}",
            *vals,
        )
    return {"status": "ok"}


@router.delete("/pipeline-templates/{template_id}")
async def delete_template(request: Request, template_id: str):
    db = get_db(request)
    await db.execute("DELETE FROM pipeline_templates WHERE id = $1", template_id)
    return {"status": "ok"}


@router.get("/export/all")
async def export_all_data(request: Request):
    db = get_db(request)
    runs = await db.fetch("SELECT * FROM pipeline_runs ORDER BY created_at DESC")
    sessions = await db.fetch("SELECT * FROM sessions ORDER BY created_at DESC")
    templates = await db.fetch("SELECT * FROM pipeline_templates ORDER BY created_at DESC")
    test_cases = await db.fetch("SELECT * FROM test_cases ORDER BY created_at DESC")
    flaky = await db.fetch("SELECT * FROM flaky_tests ORDER BY updated_at DESC")
    events = await db.fetch("SELECT * FROM pipeline_events ORDER BY created_at DESC LIMIT 500")
    return {
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "runs": [dict(r) for r in runs],
        "sessions": [dict(s) for s in sessions],
        "templates": [dict(t) for t in templates],
        "testCases": [dict(tc) for tc in test_cases],
        "flakyTests": [dict(f) for f in flaky],
        "recentEvents": [dict(e) for e in events],
    }


@router.post("/webhooks/github")
async def github_webhook(request: Request, req: WebhookPayload):
    # Q1+Q2+Q3: extend the GitHub webhook to fire TestAI runs.
    # The original handler (pre-Q1) only fired the CI runner on
    # `pull_request.opened/synchronize`. Now it ALSO fires TestAI
    # jobs on PR events (tier-2) and issue events (tier-1). The
    # CI path is preserved as a fallback.
    if req.event == "pull_request":
        pr = req.payload.get("pull_request", {})
        repo = req.payload.get("repository", {})
        action = req.payload.get("action", "")
        if action in ("opened", "synchronize"):
            full_name = repo.get("full_name", "")
            pr_number = pr.get("number", 0)
            if full_name and pr_number:
                # Always kick off TestAI in parallel with the CI run.
                # The CI result is informational; TestAI does the
                # autonomous review (tier 2 = read+write+test,
                # stops before commit_and_open_pr).
                try:
                    testai_resp = await _submit_testai_from_pr(
                        request, full_name=full_name, pr=pr, action=action,
                    )
                except Exception as exc:
                    logger.warning("GitHub PR webhook: TestAI submit failed: %s", exc)
                    testai_resp = {"status": "error", "error": str(exc)}
                # Legacy CI path (unchanged)
                token = os.environ.get("GITHUB_TOKEN", "")
                ci_req = CIRunRequest(
                    repo_url=f"https://github.com/{full_name}",
                    pr_number=pr_number, token=token, api_key="webhook",
                )
                ci_resp = await ci_run(request, ci_req)
                return {
                    "status": "queued",
                    "event": "pull_request",
                    "action": action,
                    "testai": testai_resp,
                    "ci": ci_resp,
                }
    elif req.event == "issues":
        issue = req.payload.get("issue", {})
        repo = req.payload.get("repository", {})
        action = req.payload.get("action", "")
        full_name = repo.get("full_name", "")
        # Q3: issue labeled with `bug` (or `security`/`prod` would
        # force tier 2 — but we only auto-act on `bug` for now) → tier 1.
        labels = [l.get("name", "").lower() for l in (issue.get("labels") or [])]
        if action == "opened" and full_name and issue.get("number"):
            try:
                testai_resp = await _submit_testai_from_issue(
                    request, full_name=full_name, issue=issue, tier=1,
                )
                return {
                    "status": "queued",
                    "event": "issues",
                    "action": action,
                    "testai": testai_resp,
                }
            except Exception as exc:
                logger.warning("GitHub issue webhook: TestAI submit failed: %s", exc)
                return {"status": "error", "error": str(exc)}
        if action == "labeled" and "bug" in labels and full_name and issue.get("number"):
            try:
                testai_resp = await _submit_testai_from_issue(
                    request, full_name=full_name, issue=issue, tier=1,
                )
                return {
                    "status": "queued",
                    "event": "issues",
                    "action": action,
                    "label": "bug",
                    "testai": testai_resp,
                }
            except Exception as exc:
                logger.warning("GitHub issue labeled webhook: TestAI submit failed: %s", exc)
                return {"status": "error", "error": str(exc)}
    return {"status": "ignored", "event": req.event}


async def _submit_testai_from_pr(
    request: Request, *, full_name: str, pr: dict, action: str
) -> dict:
    """Submit a tier-2 TestAI review job for a GitHub PR.

    The prompt is a natural-language description of the PR diff.
    The agent uses the PR's `head.ref` and `head.repo` to clone
    the right branch. Tier 2 = read+write+test, stops before
    `commit_and_open_pr` (Q3 decision: PR-triggered = tier 2 by
    default; a human reviews the diff before the PR auto-opens).
    """
    import asyncio
    import uuid as _uuid
    from harness.jobs.spec import JobSpec
    from harness.orchestrator import OrchestratorEngine

    head_ref = pr.get("head", {}).get("ref", "main")
    repo_url = f"https://github.com/{full_name}"
    pr_number = pr.get("number", 0)
    pr_title = pr.get("title", "")
    pr_body = pr.get("body", "") or ""
    pr_url = pr.get("html_url", "")

    prompt = (
        f"Review GitHub PR #{pr_number} on {repo_url} (branch: {head_ref}).\n\n"
        f"Title: {pr_title}\n"
        f"URL: {pr_url}\n\n"
        f"Description:\n{pr_body[:2000]}\n\n"
        "Tasks:\n"
        "1. Read the diff and understand the change.\n"
        "2. Run the test suite; flag any regressions.\n"
        "3. Post review comments on the PR via the GitHub API if any concerns.\n"
        "4. Stop before `commit_and_open_pr` — the human reviewer will approve.\n"
    )
    spec = JobSpec.from_chat_submission(
        prompt=prompt,
        repo_url=repo_url,
        branch=head_ref,
        tier=2,  # Q3: PR-triggered = supervised
        capabilities=["read", "write", "test", "run_tests"],  # no open_pr
        session_id=f"gh-pr-{pr_number}-{_uuid.uuid4()}",
        agent_id="github-pr-webhook",
    )

    engine = OrchestratorEngine()
    async def _run_in_background():
        try:
            await engine.run_job_spec(spec)
        except Exception as exc:
            logger.warning(
                "GitHub PR TestAI run failed run_id=%s: %s", spec.run_id, exc,
            )
    try:
        asyncio.create_task(_run_in_background())
    except RuntimeError:
        pass
    return {"status": "queued", "run_id": spec.run_id, "tier": 2, "source": f"github:pr:{action}"}


async def _submit_testai_from_issue(
    request: Request, *, full_name: str, issue: dict, tier: int
) -> dict:
    """Submit a tier-1 TestAI fix job for a GitHub issue.

    Q3: issue opened/labeled=bug → tier 1 (autonomous). The agent
    creates a draft PR. Tier 1 is justified here because the
    `bug` label is an explicit human signal that this should be
    fixed, and the blast radius is bounded to a draft PR (no
    auto-merge into main).
    """
    import asyncio
    import uuid as _uuid
    from harness.jobs.spec import JobSpec
    from harness.orchestrator import OrchestratorEngine

    repo_url = f"https://github.com/{full_name}"
    issue_number = issue.get("number", 0)
    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "") or ""
    issue_url = issue.get("html_url", "")

    prompt = (
        f"Fix GitHub issue #{issue_number} on {repo_url}.\n\n"
        f"Title: {issue_title}\n"
        f"URL: {issue_url}\n\n"
        f"Description:\n{issue_body[:2000]}\n\n"
        "Tasks:\n"
        "1. Understand the issue. Read the relevant code.\n"
        "2. Make the fix on a new branch.\n"
        "3. Add or update tests covering the fix.\n"
        "4. Open a DRAFT PR (not auto-merge) referencing the issue.\n"
    )
    spec = JobSpec.from_chat_submission(
        prompt=prompt,
        repo_url=repo_url,
        branch="main",  # base branch; agent creates a fix branch
        tier=tier,
        capabilities=["read", "write", "test", "run_tests", "open_pr"],
        session_id=f"gh-issue-{issue_number}-{_uuid.uuid4()}",
        agent_id="github-issue-webhook",
    )

    engine = OrchestratorEngine()
    async def _run_in_background():
        try:
            await engine.run_job_spec(spec)
        except Exception as exc:
            logger.warning(
                "GitHub issue TestAI run failed run_id=%s: %s", spec.run_id, exc,
            )
    try:
        asyncio.create_task(_run_in_background())
    except RuntimeError:
        pass
    return {"status": "queued", "run_id": spec.run_id, "tier": tier, "source": "github:issue"}


# ── Dispatcher (Q4-D reconciliation loop) ─────────────────────────


@router.get("/dispatcher/status")
async def dispatcher_status(request: Request) -> dict:
    """Return the dispatcher's current state: tick count, last tick,
    and last reconciliation summary (reclaimed / auto-blocked / swept).
    """
    dispatcher = getattr(request.app.state, "dispatcher", None)
    if dispatcher is None:
        return {"running": False, "error": "dispatcher not initialised"}
    return dispatcher.status()


@router.post("/dispatcher/tick-now")
async def dispatcher_tick_now(request: Request) -> dict:
    """Force an immediate reconciliation tick. Useful for E2E tests
    and for debugging a stuck board. Returns the per-pass counts.
    """
    dispatcher = getattr(request.app.state, "dispatcher", None)
    if dispatcher is None:
        return {"error": "dispatcher not initialised"}
    return await dispatcher.tick()


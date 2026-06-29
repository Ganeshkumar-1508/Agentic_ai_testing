from __future__ import annotations

import os
from typing import Any

import httpx


class GitProvider:
    name: str = ""

    async def list_open_prs(self, repo: str, token: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def list_open_issues(self, repo: str, token: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_pr_detail(self, repo: str, pr_number: int, token: str) -> dict[str, Any]:
        raise NotImplementedError

    async def get_pr_diff(self, repo: str, pr_number: int, token: str) -> str:
        raise NotImplementedError

    async def get_pr_files(self, repo: str, pr_number: int, token: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_ci_checks(self, repo: str, ref: str, token: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def post_pr_comment(self, repo: str, pr_number: int, token: str, body: str) -> None:
        raise NotImplementedError

    async def add_labels(self, repo: str, issue_number: int, token: str, labels: list[str]) -> None:
        raise NotImplementedError

    async def set_commit_status(self, repo: str, sha: str, token: str, state: str, description: str, context: str = "testai") -> None:
        raise NotImplementedError


class GitHubProvider(GitProvider):
    name = "github"

    def __init__(self) -> None:
        self.base = "https://api.github.com"

    def _headers(self, token: str, accept: str = "application/vnd.github.v3+json") -> dict[str, str]:
        h = {"Accept": accept}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def list_open_prs(self, repo: str, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/repos/{repo}/pulls?state=open&per_page=50"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "body": (pr.get("body") or "")[:500],
                    "head_sha": pr["head"]["sha"],
                    "base_sha": pr["base"]["sha"],
                    "source_branch": pr["head"]["ref"],
                    "target_branch": pr["base"]["ref"],
                    "user": pr["user"]["login"],
                    "changed_files": pr.get("changed_files", 0),
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "labels": [l["name"] for l in pr.get("labels", [])],
                    "reviewers": [r["login"] for r in pr.get("requested_reviewers", [])],
                    "created_at": pr["created_at"],
                    "updated_at": pr["updated_at"],
                    "mergeable_state": pr.get("mergeable_state", "unknown"),
                    "draft": pr.get("draft", False),
                }
                for pr in data
            ]

    async def list_open_issues(self, repo: str, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/repos/{repo}/issues?state=open&per_page=50&sort=created&direction=desc"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": (issue.get("body") or "")[:500],
                    "user": issue["user"]["login"],
                    "labels": [l["name"] for l in issue.get("labels", [])],
                    "state": issue["state"],
                    "created_at": issue["created_at"],
                    "updated_at": issue["updated_at"],
                    "is_pull_request": "pull_request" in issue,
                }
                for issue in data
                if "pull_request" not in issue
            ]

    async def get_pr_detail(self, repo: str, pr_number: int, token: str) -> dict[str, Any]:
        url = f"{self.base}/repos/{repo}/pulls/{pr_number}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            pr = r.json()
            return {
                "number": pr["number"],
                "title": pr["title"],
                "body": (pr.get("body") or "")[:2000],
                "state": pr["state"],
                "head_sha": pr["head"]["sha"],
                "base_sha": pr["base"]["sha"],
                "source_branch": pr["head"]["ref"],
                "target_branch": pr["base"]["ref"],
                "user": pr["user"]["login"],
                "changed_files": pr.get("changed_files", 0),
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "labels": [l["name"] for l in pr.get("labels", [])],
                "reviewers": [r["login"] for r in pr.get("requested_reviewers", [])],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
                "mergeable": pr.get("mergeable"),
                "mergeable_state": pr.get("mergeable_state", "unknown"),
                "merged": pr.get("merged", False),
                "draft": pr.get("draft", False),
            }

    async def get_pr_diff(self, repo: str, pr_number: int, token: str) -> str:
        url = f"{self.base}/repos/{repo}/pulls/{pr_number}"
        headers = self._headers(token, accept="application/vnd.github.v3.diff")
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            return r.text

    async def get_pr_files(self, repo: str, pr_number: int, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/repos/{repo}/pulls/{pr_number}/files?per_page=100"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "filename": f["filename"],
                    "status": f["status"],
                    "additions": f["additions"],
                    "deletions": f["deletions"],
                    "changes": f["changes"],
                    "patch": (f.get("patch") or "")[:2000],
                }
                for f in data
            ]

    async def get_ci_checks(self, repo: str, ref: str, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/repos/{repo}/commits/{ref}/check-runs?per_page=100"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "name": cr["name"],
                    "status": cr["status"],
                    "conclusion": cr.get("conclusion"),
                    "started_at": cr.get("started_at"),
                    "completed_at": cr.get("completed_at"),
                    "output_title": (cr.get("output") or {}).get("title", ""),
                    "output_summary": (cr.get("output") or {}).get("summary", "")[:500],
                }
                for cr in data.get("check_runs", [])
            ]

    async def post_pr_comment(self, repo: str, pr_number: int, token: str, body: str) -> None:
        url = f"{self.base}/repos/{repo}/issues/{pr_number}/comments"
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=self._headers(token), json={"body": body}, timeout=10)
            r.raise_for_status()

    async def add_labels(self, repo: str, issue_number: int, token: str, labels: list[str]) -> None:
        url = f"{self.base}/repos/{repo}/issues/{issue_number}/labels"
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=self._headers(token), json={"labels": labels}, timeout=10)
            r.raise_for_status()

    async def set_commit_status(self, repo: str, sha: str, token: str, state: str, description: str, context: str = "testai") -> None:
        url = f"{self.base}/repos/{repo}/statuses/{sha}"
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url, headers=self._headers(token),
                json={"state": state, "description": description, "context": context},
                timeout=10,
            )
            r.raise_for_status()


class GitLabProvider(GitProvider):
    name = "gitlab"

    def __init__(self) -> None:
        self.base = "https://gitlab.com/api/v4"

    def _headers(self, token: str) -> dict[str, str]:
        return {"PRIVATE-TOKEN": token} if token else {}

    def _encoded(self, repo: str) -> str:
        return repo.replace("/", "%2F")

    async def list_open_prs(self, repo: str, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/projects/{self._encoded(repo)}/merge_requests?state=opened&per_page=50"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "number": mr["iid"],
                    "title": mr["title"],
                    "body": (mr.get("description") or "")[:500],
                    "head_sha": mr["sha"],
                    "base_sha": mr.get("diff_refs", {}).get("base_sha", ""),
                    "source_branch": mr["source_branch"],
                    "target_branch": mr["target_branch"],
                    "user": mr["author"]["username"],
                    "changed_files": mr.get("changes_count", 0),
                    "additions": 0,
                    "deletions": 0,
                    "labels": mr.get("labels", []),
                    "created_at": mr["created_at"],
                    "updated_at": mr["updated_at"],
                    "merge_status": mr.get("detailed_merge_status", "unknown"),
                    "draft": mr.get("draft", False),
                }
                for mr in data
            ]

    async def list_open_issues(self, repo: str, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/projects/{self._encoded(repo)}/issues?state=opened&per_page=50&sort=created_at&direction=desc"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "number": issue["iid"],
                    "title": issue["title"],
                    "body": (issue.get("description") or "")[:500],
                    "user": issue["author"]["username"],
                    "labels": [l["title"] for l in issue.get("labels", [])] if isinstance(issue.get("labels"), list) else [],
                    "state": issue["state"],
                    "created_at": issue["created_at"],
                    "updated_at": issue["updated_at"],
                    "is_pull_request": False,
                }
                for issue in data
            ]

    async def get_pr_detail(self, repo: str, pr_number: int, token: str) -> dict[str, Any]:
        url = f"{self.base}/projects/{self._encoded(repo)}/merge_requests/{pr_number}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            mr = r.json()
            return {
                "number": mr["iid"],
                "title": mr["title"],
                "body": (mr.get("description") or "")[:2000],
                "state": mr["state"],
                "head_sha": mr["sha"],
                "base_sha": mr.get("diff_refs", {}).get("base_sha", ""),
                "source_branch": mr["source_branch"],
                "target_branch": mr["target_branch"],
                "user": mr["author"]["username"],
                "changed_files": mr.get("changes_count", 0),
                "labels": mr.get("labels", []),
                "created_at": mr["created_at"],
                "updated_at": mr["updated_at"],
                "merge_status": mr.get("detailed_merge_status", "unknown"),
                "draft": mr.get("draft", False),
                "merged": mr.get("merged", False),
            }

    async def get_pr_diff(self, repo: str, pr_number: int, token: str) -> str:
        url = f"{self.base}/projects/{self._encoded(repo)}/merge_requests/{pr_number}/diffs?unidiff=true"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            data = r.json()
            diffs = [d.get("diff", "") for d in data]
            return "\n".join(diffs)

    async def get_pr_files(self, repo: str, pr_number: int, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/projects/{self._encoded(repo)}/merge_requests/{pr_number}/diffs?unidiff=true"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "filename": d.get("new_path", ""),
                    "status": "added" if d.get("new_file") else "deleted" if d.get("deleted_file") else "modified",
                    "additions": 0,
                    "deletions": 0,
                    "changes": 0,
                    "patch": (d.get("diff") or "")[:2000],
                }
                for d in data
            ]

    async def get_ci_checks(self, repo: str, ref: str, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/projects/{self._encoded(repo)}/pipelines?ref={ref}&per_page=20"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self._headers(token), timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "name": f"pipeline-{p['id']}",
                    "status": p["status"],
                    "conclusion": p["status"],
                    "started_at": p.get("created_at"),
                    "completed_at": p.get("updated_at"),
                    "output_title": f"Pipeline #{p['id']}",
                    "output_summary": f"Pipeline {p['status']} on {p.get('ref', 'unknown')}",
                }
                for p in data
            ]

    async def post_pr_comment(self, repo: str, pr_number: int, token: str, body: str) -> None:
        url = f"{self.base}/projects/{self._encoded(repo)}/merge_requests/{pr_number}/notes"
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=self._headers(token), json={"body": body}, timeout=10)
            r.raise_for_status()

    async def add_labels(self, repo: str, issue_number: int, token: str, labels: list[str]) -> None:
        url = f"{self.base}/projects/{self._encoded(repo)}/merge_requests/{issue_number}"
        async with httpx.AsyncClient() as client:
            r = await client.put(url, headers=self._headers(token), json={"add_labels": ",".join(labels)}, timeout=10)
            r.raise_for_status()

    async def set_commit_status(self, repo: str, sha: str, token: str, state: str, description: str, context: str = "testai") -> None:
        url = f"{self.base}/projects/{self._encoded(repo)}/statuses/{sha}"
        state_map = {"pending": "pending", "success": "success", "failure": "failed", "error": "failed"}
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=self._headers(token), json={"state": state_map.get(state, state), "description": description, "name": context}, timeout=10)
            r.raise_for_status()


class BitbucketProvider(GitProvider):
    name = "bitbucket"

    def __init__(self) -> None:
        self.base = "https://api.bitbucket.org/2.0"

    async def list_open_prs(self, repo: str, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/repositories/{repo}/pullrequests?state=OPEN&pagelen=50"
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "number": pr["id"],
                    "title": pr["title"],
                    "body": (pr.get("description") or "")[:500],
                    "head_sha": pr["source"]["commit"]["hash"],
                    "base_sha": pr["destination"]["commit"]["hash"],
                    "user": pr["author"]["display_name"],
                    "changed_files": 0,
                    "additions": 0,
                    "deletions": 0,
                    "labels": [],
                    "created_at": pr["created_on"],
                    "updated_at": pr["updated_on"],
                }
                for pr in data.get("values", [])
            ]

    async def get_pr_detail(self, repo: str, pr_number: int, token: str) -> dict[str, Any]:
        url = f"{self.base}/repositories/{repo}/pullrequests/{pr_number}"
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            pr = r.json()
            return {
                "number": pr["id"],
                "title": pr["title"],
                "body": (pr.get("description") or "")[:2000],
                "state": pr["state"],
                "head_sha": pr["source"]["commit"]["hash"],
                "base_sha": pr["destination"]["commit"]["hash"],
                "user": pr["author"]["display_name"],
                "changed_files": 0,
                "labels": [],
                "created_at": pr["created_on"],
                "updated_at": pr["updated_on"],
            }

    async def get_pr_diff(self, repo: str, pr_number: int, token: str) -> str:
        url = f"{self.base}/repositories/{repo}/pullrequests/{pr_number}/diff"
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            return r.text

    async def get_pr_files(self, repo: str, pr_number: int, token: str) -> list[dict[str, Any]]:
        url = f"{self.base}/repositories/{repo}/pullrequests/{pr_number}/diffstat"
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "filename": f.get("new", {}).get("path", ""),
                    "status": f.get("status", "modified"),
                    "additions": f.get("lines_added", 0),
                    "deletions": f.get("lines_removed", 0),
                    "changes": f.get("lines_added", 0) + f.get("lines_removed", 0),
                    "patch": "",
                }
                for f in data.get("values", [])
            ]

    async def get_ci_checks(self, repo: str, ref: str, token: str) -> list[dict[str, Any]]:
        return []

    async def post_pr_comment(self, repo: str, pr_number: int, token: str, body: str) -> None:
        url = f"{self.base}/repositories/{repo}/pullrequests/{pr_number}/comments"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient() as client:
            payload = {"content": {"raw": body}}
            await client.post(url, headers=headers, json=payload, timeout=10)

    async def add_labels(self, repo: str, issue_number: int, token: str, labels: list[str]) -> None:
        pass

    async def set_commit_status(self, repo: str, sha: str, token: str, state: str, description: str, context: str = "testai") -> None:
        pass


class LocalProvider(GitProvider):
    """Works with local git repositories on the filesystem."""

    name = "local"

    async def list_open_prs(self, repo: str, token: str = "") -> list[dict[str, Any]]:
        import subprocess
        repo_path = repo
        branches: list[dict[str, Any]] = []
        try:
            result = subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                capture_output=True, text=True, timeout=15, cwd=repo_path,
            )
            all_branches = [b.strip() for b in result.stdout.splitlines() if b.strip()]
            base_branch = "main"
            for rb in all_branches:
                if rb in ("origin/main", "origin/master", "origin/HEAD", "origin", "main", "master"):
                    continue
                branch_name = rb.split("/", 1)[-1] if "/" in rb else rb
                diff_result = subprocess.run(
                    ["git", "diff", base_branch + "..." + rb, "--stat"],
                    capture_output=True, text=True, timeout=15, cwd=repo_path,
                )
                stats = diff_result.stdout.strip()
                files_changed = len([l for l in stats.split("\n") if l.strip()]) if stats else 0
                branches.append({
                    "number": len(branches) + 1,
                    "title": f"[local] {branch_name}",
                    "body": f"Local branch: {branch_name}\n{stats[:500]}",
                    "head_sha": branch_name,
                    "base_sha": "main",
                    "source_branch": branch_name,
                    "target_branch": "main",
                    "user": "local",
                    "changed_files": files_changed,
                    "additions": 0,
                    "deletions": 0,
                    "labels": ["local"],
                    "reviewers": [],
                    "created_at": "",
                    "updated_at": "",
                })
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("LocalProvider: failed to list branches: %s", e)
        return branches

    async def list_open_issues(self, repo: str, token: str = "") -> list[dict[str, Any]]:
        return []

    async def get_pr_detail(self, repo: str, pr_number: int, token: str = "") -> dict[str, Any]:
        return {"number": pr_number, "title": f"[local] branch-{pr_number}", "state": "open"}

    async def get_pr_diff(self, repo: str, pr_number: int, token: str = "") -> str:
        import subprocess
        try:
            result = subprocess.run(
                ["git", "diff", "origin/main...origin/" + str(pr_number)],
                capture_output=True, text=True, timeout=15, cwd=repo,
            )
            return result.stdout
        except Exception as e:
            return f"Error getting diff: {e}"

    async def get_pr_files(self, repo: str, pr_number: int, token: str = "") -> list[dict[str, Any]]:
        return []

    async def get_ci_checks(self, repo: str, ref: str, token: str = "") -> list[dict[str, Any]]:
        return []

    async def post_pr_comment(self, repo: str, pr_number: int, token: str, body: str) -> None:
        import logging
        import os
        output_dir = os.path.join(repo, ".testai", "pr-comments")
        os.makedirs(output_dir, exist_ok=True)
        import datetime
        path = os.path.join(output_dir, f"pr-{pr_number}-{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        with open(path, "w") as f:
            f.write(body)
        logging.getLogger(__name__).info("LocalProvider: PR comment saved to %s", path)

    async def add_labels(self, repo: str, issue_number: int, token: str, labels: list[str]) -> None:
        pass

    async def set_commit_status(self, repo: str, sha: str, token: str, state: str, description: str, context: str = "testai") -> None:
        import logging
        logging.getLogger(__name__).info("LocalProvider: commit %s status -> %s: %s", sha[:8], state, description)


def get_provider_from_url(url: str) -> tuple[str, str, str] | None:
    """Detect git platform from URL. Returns (provider_name, repo_path, raw_url)."""
    import re
    patterns = [
        (r"github\.com[/:]([^/]+/[^/\s]+?)(?:\.git)?(?:/.*)?$", "github"),
        (r"gitlab\.com[/:]([^/]+/[^/\s]+?)(?:\.git)?(?:/.*)?$", "gitlab"),
        (r"bitbucket\.org[/:]([^/]+/[^/\s]+?)(?:\.git)?(?:/.*)?$", "bitbucket"),
    ]
    for pattern, provider in patterns:
        m = re.search(pattern, url)
        if m:
            repo = m.group(1).replace(".git", "")
            raw = f"https://{provider}.com/{repo}"
            return provider, repo, raw
    return None


def get_provider(provider_name: str) -> GitProvider:
    providers = {
        "github": GitHubProvider,
        "gitlab": GitLabProvider,
        "bitbucket": BitbucketProvider,
        "local": LocalProvider,
    }
    cls = providers.get(provider_name)
    if not cls:
        raise ValueError(f"Unsupported provider: {provider_name}")
    return cls()

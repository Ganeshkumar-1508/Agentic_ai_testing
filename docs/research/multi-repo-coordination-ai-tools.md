# Multi-Repo Coordination for AI Coding Tools — Research Report

> **Date:** 2026-06-05  
> **Scope:** Real-world implementations, platforms, and technical patterns for coordinating pull requests across multiple repositories using AI agents and CI/CD tooling.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Consolidated Comparison Table](#consolidated-comparison-table)
3. [Platform Deep-Dives](#platform-deep-dives)
    - [Tembo](#1-tembo)
    - [Sweep AI](#2-sweep-ai)
    - [GitHub Agentic Workflows](#3-github-agentic-workflows)
    - [Claude Code Multi-Repo Toolkit (Enigmatica)](#4-claude-code-multi-repo-toolkit)
    - [Mergify](#5-mergify)
    - [Zuul CI](#6-zuul-ci)
    - [depends-on/depends-on-action (GitHub Action)](#7-depends-ondepends-on-action)
    - [build-chain (KIE)](#8-build-chain-kie)
    - [Augment Code](#9-augment-code)
    - [agent-worktree](#10-agent-worktree)
4. [Technical Patterns Catalog](#technical-patterns-catalog)
5. [Data Model Comparison](#data-model-comparison)
6. [Recommendations for Implementation](#recommendations-for-implementation)

---

## Executive Summary

This research surveyed **10 distinct platforms/tools** that address the multi-repo coordination problem. The approaches fall into **4 architectural categories**:

| Category | Description | Examples |
|---|---|---|
| **AI Orchestration Layer** | Agent-agnostic platforms that route tasks to coding agents and manage multi-repo workflows | Tembo, GitHub Agentic Workflows |
| **AI Agent with Multi-Repo Support** | Single AI coding agent that natively opens PRs across repos | Sweep AI (limited), Claude Code |
| **CI/CD Cross-Project Dependency** | Pipeline tools that model and enforce cross-repo PR ordering | Zuul CI, Mergify, build-chain (KIE) |
| **Git Worktree Pattern** | Local multi-agent parallelism by isolating working directories | agent-worktree, Worktrunk |
| **GitHub Action Ecosystem** | Composible GitHub Actions that declare and resolve cross-repo deps | depends-on-action |
| **IDE-Level Context** | Tools that build cross-repo dependency maps at analysis time | Augment Code |

---

## Consolidated Comparison Table

| Tool / Platform | Type | Multi-Repo Mechanism | PR Linking? | Auth Per Repo | Data Model | Open Source? | Key Technical Pattern |
|---|---|---|---|---|---|---|---|
| **Tembo** | AI Orchestration | Single task → opens PRs in each repo simultaneously; agent-agnostic routing | ✅ Links PRs with cross-references | Per-repo via OAuth (GitHub/GitLab/Bitbucket) | `Workspace` → `Repos` → `Tasks` → `PRs` | ❌ Proprietary ($60/mo+, self-hosted available) | Agent-agnostic orchestration; `@tembo` mention triggers; signed + verified commits |
| **Sweep AI** | AI Agent (GitHub Issue → PR) | Single-repo focused; handles one issue → one PR per repo; multi-file within a repo | ❌ No built-in cross-repo linking | GitHub App OAuth | `Issue` → `FileChangeRequest[]` → `PR` | ✅ Apache 2.0 (sweepai/sweep) | Vector DB code search; AI plans changes per file then creates PR |
| **GitHub Agentic Workflows** | CI-native AI automation | Markdown-defined workflows run in Actions; can target multi-repo via separate workflows | ✅ Via action dependencies | OAuth + GitHub App permissions | `.md` workflow → `.lock.yml` → Actions run | ✅ Via `gh-aw` extension | "Safe outputs" for write ops; read-only by default; defense-in-depth |
| **Claude Code (Enigmatica guide)** | AI CLI + custom toolkit | CLI tool with `Workspace` type modeling dependent repos; creates coordinated PRs via `gh` | ✅ Links PRs with cross-references and merge-order | Per-repo GitHub tokens | `Workspace{name, repos[], conventions}` → `CrossRepoChange{id, RepoChange[], status, depOrder}` | ❌ Reference architecture only | Dependency-ordered PR creation; `npm link` for local deps during change |
| **Mergify** | CI/CD queue manager | `Depends-On:` header in PR body; queues PRs in dependency order | ✅ `Depends-On: <PR url>` syntax | GitHub App (per-repo install) | `Depends-On` header → `queue_rules` → `merge_conditions` | ❌ Proprietary (free for public repos) | Directed acyclic graph of PRs; automatic merge ordering |
| **Zuul CI** | CI/CD gating system | Cross-project dependencies via `Depends-On:` footer in commit message/PR | ✅ `Depends-On: <change-url>` | Per-project auth in tenant config | `Pipeline` → `Change Queue` → DAG of `Changes` across projects | ✅ Apache 2.0 (zuul/zuul) | Speculative parallel execution; DAG-based dependency model; project gating |
| **depends-on-action** | GitHub Action | Extracts `Depends-On:` lines from PR description; modifies go.mod/package.json/requirements.txt | ✅ `Depends-On: <PR url>` | `GITHUB_TOKEN` + optional `GITLAB_TOKEN` | `Depends-On` header → dependency injection per language | ✅ MIT (depends-on/depends-on-action) | Language-aware dependency injection; supports Go/Python/JS/Ansible/Container |
| **build-chain (KIE)** | CI orchestrator | Cross-repo PR dependency building | ✅ | GitHub tokens | Unknown (proprietary KIE tooling) | ❌ (internal KIE tool) | Dependency traversal; multi-repo build coordination |
| **Augment Code** | IDE Code AI | Cross-repo context via "COD Model"; dependency graph visualization | ❌ (analysis only, no PR creation) | IDE auth + GitHub connection | Live dependency graph of imports/calls across repos | ❌ Proprietary | Definitive (not probabilistic) dependency chains; 200K+ token context |
| **agent-worktree** | Git worktree manager | One worktree per agent; parallel execution on same repo | ❌ No PR linking | Local only | `Worktree` per branch → `base_branch` → `squash/merge` | ✅ MIT (nekocode/agent-worktree) | "Snap" mode: create worktree → run agent → auto-cleanup; CLI for `wt` |

---

## Platform Deep-Dives

### 1. Tembo

**Type:** AI Orchestration Layer  
**URL:** https://tembo.ai | https://docs.tembo.io/features/pull-requests

Tembo is an **agent-agnostic orchestration platform** — it doesn't build its own agent but routes tasks to Claude Code, Codex, Cursor, Amp, or OpenCode.

**Multi-Repo Problem Solving:**
> "If a session spans multiple repositories, Tembo opens a pull request or merge request in each one."
> "It can also coordinate changes across supported git providers, including GitHub, GitLab, and Bitbucket."

**Technical architecture:**
1. **Detection** — Issues identified via integrations (Sentry errors, Linear tickets) or direct `@tembo` mention
2. **Execution** — Coding agent analyzes codebase and generates solution in isolated sandbox
3. **Pull Request** — Changes submitted with problem/solution context in each affected repo
4. **Feedback Loop** — `@tembo` mentions in PR comments trigger iterations

**Data Model:**
- `Workspace` → collection of repositories
- `Task` → unit of work that can span multiple repos
- `Credit` → consumption-based billing per task
- `Rule files` → per-repo coding standards

**PR Characteristics:**
- Clear description of problem/solution
- Follows coding standards via rule files
- Links to original issue/error/session
- Tests when appropriate
- Signed & verified commits (GitHub)
- Uses PR templates (`/.github/pull_request_template.md`, `/docs/pull_request_template.md`, `/pull_request_template.md`)

**Key Innovation:** Agent-agnostic routing — teams can switch between Claude Code, Codex, Cursor, etc. per task without changing workflow.

**Strengths for multi-repo:**
- Works across git providers (GitHub, GitLab, Bitbucket)
- Single task can update API, client libraries, and docs together
- Team control preserved (Tembo proposes, humans approve)

**Limitations:**
- Credit-based pricing can be expensive for heavy use
- Quality depends on which agent is routed to
- Not open source, but self-hosted option available for enterprise

---

### 2. Sweep AI

**Type:** AI Agent (GitHub Issue → PR)  
**URL:** https://github.com/sweepai/sweep | https://docs.sweep.dev/

Sweep AI is an **open-source AI agent** that turns GitHub issues into code changes via pull requests. It integrates directly with GitHub through webhooks.

**Multi-Repo Problem Solving:**
Sweep AI is **primarily single-repo focused**. It handles one issue → one PR within one repository. However, its architecture has patterns that could be extended:

**Core Entity — FileChangeRequest (FCR):**
```python
# sweepai/core/entities.py
class FileChangeRequest:
    """Core entity for representing a desired change to a file."""
    file_path: str
    instructions: str
    change_type: str  # create, modify, delete
    metadata: dict
```

**Event Processing Flow:**
```
GitHub Webhook → sweepai/api.py → Handler (on_ticket/on_comment)
  → Vector DB search (code understanding)
  → FileChangeRequest[] generation (AI planning)
  → create_pr.py → GitHub API (PR creation)
```

**Auth:** GitHub App OAuth — single app installation per org, then per-repo access.

**Key limitation for multi-repo:** No native `CrossRepoChange` entity. Sweep handles one ticket → one PR. To extend to multi-repo, you'd need an orchestrator that creates separate Sweep tickets per repo, or modifies the `on_ticket` handler to create PRs in multiple repos.

**Why Sweep matters:** It's the most **referenceable open-source** implementation at scale (6,000+ GitHub stars). The `FileChangeRequest` entity pattern, the `Vector DB` code search, and the handler architecture are all directly usable patterns.

---

### 3. GitHub Agentic Workflows

**Type:** CI-native AI automation  
**URL:** https://github.blog/ai-and-ml/automate-repository-tasks-with-github-agentic-workflows/

**Status:** Technical preview (Feb 2026)

GitHub Agentic Workflows bring **coding agents into GitHub Actions** using plain Markdown description files.

**Workflow definition (.md file):**
```markdown
---
on: schedule: daily
permissions:
  contents: read
  issues: read
  pull-requests: read
safe-outputs:
  create-issue:
    title-prefix: "[repo status] "
    labels: [report]
tools:
  github: {}
---

# Daily Repo Status Report
Create a daily status report for maintainers.
Include recent repository activity...
```

**Multi-Repo Handling:**
Since these are standard Actions workflows, you could create one workflow per repo or use matrix strategies. The blog doesn't detail a specific multi-repo entity model, but the `safe-outputs` model with explicit permission boundaries is a key architectural pattern.

**Security Architecture (defense-in-depth):**
1. Read-only permissions by default
2. Write operations require explicit `safe-outputs` approval
3. Sandboxed execution
4. Tool allowlisting
5. Network isolation

**Supported Agents:** Copilot CLI, Claude Code, or OpenAI Codex

**Why this matters:** This is GitHub-native — runs in the same infrastructure as Actions. The pattern of `.md` workflow files with frontmatter + safe-outputs is referenceable for any tool building guard-railed AI automation.

---

### 4. Claude Code Multi-Repo Toolkit (Enigmatica Guide)

**Type:** Reference Architecture / CLI Toolkit  
**URL:** https://enigmatica.ai/coding/multi-repository-management-with-ai

**This is the most detailed reference architecture** for AI-driven multi-repo coordination found in this research. It's a guide for building a CLI tool using Claude Code, but the data model and workflow patterns are directly applicable.

**Data Model:**
```typescript
// src/config.ts
type Workspace = {
  name: string;
  repos: RepoConfig[];
  conventions: {
    branchNamingPattern: string;
    commitMessageFormat: string;
    prTemplatePath: string;
  };
};

type RepoConfig = {
  name: string;
  path: string;         // local disk path
  githubUrl: string;
  defaultBranch: string;
  dependencies: string[]; // names of other repos in workspace
};

// src/lib/cross-change.ts
type CrossRepoChange = {
  id: string;
  description: string;
  repoChanges: RepoChange[];
  status: 'planning' | 'in_progress' | 'reviewing' | 'merged';
  dependencyOrder: string[]; // which repo changes must merge first
};

type RepoChange = {
  repoName: string;
  branchName: string;
  fileChanges: FileChange[];
  commitMessage: string;
};
```

**Cross-Repo Change Workflow:**
1. **Analyze** — Scan all repos for affected files (e.g., rename `fullName` → `displayName`)
2. **Plan** — Generate `CrossRepoChange` with dependency order (shared types → API → frontend+mobile → docs)
3. **Dry-run** — Show diffs before executing
4. **Execute** — For each repo in dependency order:
   - Checkout default branch → pull → create feature branch
   - Apply file changes
   - Run linter + tests
   - Commit with reference to cross-repo change ID
5. **PR** — Create coordinated PRs with:
   - Summary of overall change
   - Links to related PRs in other repos
   - Merge order specification
   - Pre-merge requirements
6. **Merge** — Process PRs in dependency order, waiting for CI/publish at each step

**Coordinated PR Creation:**
```bash
# Each PR description includes:
# - Overall change summary
# - Links to related PRs in other repos
# - Merge order
gh pr create --title "..." --body "Cross-repo change ID:...
Depends on: #123 in shared-types"
```

**Dependency Tracking:**
- Scans `package.json`, `pyproject.toml`, etc. for internal workspace dependencies
- Generates dependency graph with circular detection
- Detects version mismatches across repos (e.g., react 18.2.0 vs 18.1.0)
- `npm link` or workspace protocols for local linking during changes

**Key Pattern:** **Bottom-up propagation** — always update from the bottom of the dependency tree upward.

---

### 5. Mergify

**Type:** CI/CD queue manager  
**URL:** https://dashboard.mergify.com/ | https://github.com/apps/mergify

**Multi-Repo Problem Solving:**
Mergify handles inter-PR dependencies using a `Depends-On` header in the PR body:

```
Depends-On: https://github.com/org/library/pull/123
```

**Data Model:**
```yaml
# .mergify.yml
queue_rules:
  - name: default
    merge_conditions:
      - label=merge

pull_request_rules:
  - name: dependency rules
    conditions:
      - files~=package.json
    actions:
      queue:
        name: default
```

**How it works:**
1. User adds `Depends-On: <PR url>` to PR description
2. Mergify detects the dependency header
3. Creates a queue ordering respecting dependencies
4. Waits to merge until all linked PRs are successfully merged
5. Automatically merges in dependency order

**Auth:** GitHub App — installed per-repository or per-organization

**Why this matters:** Simplest dependency declaration model found — just a header in the PR body. No complex config. The `Depends-On` syntax is becoming a de facto standard (also used by Zuul and depends-on-action).

---

### 6. Zuul CI

**Type:** CI/CD gating system  
**URL:** https://zuul-ci.org/docs/zuul/latest/gating.html

Zuul is the **most sophisticated open-source CI/CD system** for cross-project dependencies. Built by OpenStack, used by massive multi-repo projects.

**Cross-Project Dependency Model:**
```
Depends-On: https://github.com/org/repo/pull/123
```

This footer is added to commit messages (Gerrit) or PR descriptions (GitHub).

**Dependency Architecture:**
- **Directed Acyclic Graph (DAG)** — dependencies form a DAG, just like git itself
- **Shared change queue** — projects in a shared queue are tested together
- **Speculative parallel execution** — tests changes in parallel assuming dependencies will pass
- If a change fails, downstream changes are re-tested without it

**Pipeline Types:**
1. **Dependent pipeline** — changes tested in order (gating); parallel with speculative execution
2. **Independent pipeline** — no ordering, each change tested independently
3. **Serial pipeline** — one change at a time

**Window Algorithm (flow control):**
- Starts at 20 parallel changes
- Each successful merge → window +1
- Each failure → window halved
- Floor: minimum parallel tests always running
- Ceiling: prevents starving other pipelines

**Auth:** Per-project authentication in tenant configuration. Supports GitHub, Gerrit, GitLab, Pagure.

**Why this matters:** Zuul is production-proven at massive scale (OpenStack, 1000s of developers). Its speculative parallel execution algorithm is state-of-the-art for cross-repo dependency testing.

---

### 7. depends-on/depends-on-action

**Type:** GitHub Action  
**URL:** https://github.com/depends-on/depends-on-action  
**License:** MIT (16 stars, 2 forks)

**Multi-Repo Problem Solving:**
This GitHub Action extracts `Depends-On:` lines from a PR description, then injects the dependency's changes into the current PR's test environment.

**Language-Specific Dependency Injection:**
| Language | Mechanism |
|---|---|
| **Go** | Adds `replace` directives to `go.mod` |
| **Python** | Replaces entries in `requirements.txt` or `pyproject.toml` with `-e <local change>` |
| **JavaScript** | Replaces entries in `package.json` with `file:<local change>` |
| **Ansible** | Replaces entries in `requirements.yml` |
| **Container** | Auto-detects containers and injects changes |

**Depends-On Syntax:**
```
Depends-On: https://github.com/org/library/pull/123
Depends-On: https://github.com/org/library/pull/456?subdir=packages/foo
Depends-On: https://gerrit-review.googlesource.com/c/gerrit/+/394841
Depends-On: https://gitlab.com/org/project/-/merge_requests/428
```

**Workflow Example:**
```yaml
name: Pull Request
on: pull_request: [opened, synchronize, reopened]
jobs:
  validate-tests:
    steps:
      - uses: actions/checkout@v4
      - uses: depends-on/depends-on-action@0.16.0
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
```

**Why this matters:** Smallest composable unit for cross-repo PR testing. The language-aware dependency injection pattern is directly referenceable.

---

### 8. build-chain (KIE / Red Hat)

**Type:** CI orchestrator for cross-repo PRs  
**URL:** https://blog.kie.org/2021/07/cross-repo-pull-requests-build-chain-tool-to-the-rescue.html

Used by the KIE (Knowledge Is Everything) group at Red Hat for coordinating PRs across the Drools, jBPM, and OptaPlanner projects.

**Multi-Repo Problem Solving:**
> "How can we assure one specific pull request will work with the latest changes from/in the dependant/dependency projects and it won't break something?"

**Key Features:**
- Dependency traversal across repos
- Build coordination for multi-repo PRs
- Ensures PRs work with latest changes from dependent projects

**Why this matters:** While the tool itself is proprietary/internal to Red Hat, the problem statement is classic and the cross-repo "build chain" concept is referenceable.

---

### 9. Augment Code

**Type:** IDE AI with cross-repo context  
**URL:** https://www.augmentcode.com/

Augment is an AI coding assistant with a unique **cross-repository dependency mapping** capability.

**Key Technical Features:**
- **COD Model** — parses source code, extracts every import and call, builds interactive maps of system connections across repositories
- **200,000+ token context** — can load multiple repositories simultaneously
- **ISO/IEC 42001:2023** — first AI coding assistant with certified AI governance
- **60% reduction** in cross-repo refactoring time (claimed)

**Multi-Repo Handling:**
Augment doesn't create PRs — it's an IDE tool for **understanding** cross-repo dependencies before making changes. Its live dependency graph shows definitive (not probabilistic) dependency chains.

**Why this matters:** The dependency mapping pattern (parsing imports/calls to build a graph) is the foundation for any multi-repo coordination tool. Without this understanding, you can't plan cross-repo changes.

---

### 10. agent-worktree

**Type:** Git worktree manager for AI agents  
**URL:** https://github.com/nekocode/agent-worktree  
**License:** MIT (260 stars, 16 forks)

**Multi-Repo Problem Solving:**
Rather than PR coordination, agent-worktree solves the **parallel agent execution** problem — running multiple AI agents on the same repository simultaneously without conflicts.

**Architecture:**
```
Main Repo
├── .git
├── worktrees/
│   ├── feature-x/     ← agent 1 workspace
│   ├── fix-bug-y/     ← agent 2 workspace
│   └── refactor-z/    ← agent 3 workspace
```

**Key Commands:**
```bash
wt new feature-x           # Create worktree + enter
wt new -s claude           # Snap mode: create → run agent → auto-cleanup
wt ls                      # List all worktrees with base branch info
wt merge -d                # Merge and delete worktree
wt sync                    # Rebase from base branch
```

**Snap Mode Flow:**
1. `wt new -s claude` → creates worktree with random branch
2. Agent runs inside worktree
3. On agent exit:
   - No changes → cleanup
   - Only commits → prompt to merge
   - Uncommitted changes → prompt to reopen agent or commit manually

**Why this matters:** For multi-repo AI tools, the ability to run agents in parallel (even on the same repo) is foundational. The worktree pattern cleanly solves workspace isolation without Docker containers.

---

## Technical Patterns Catalog

Here are the **technical patterns** extracted from all surveyed approaches:

### Pattern 1: `Depends-On` Header Convention

**Used by:** Mergify, Zuul CI, depends-on-action  
**Mechanism:** A footer/header in the PR body or commit message  
**Format:** `Depends-On: <PR URL>`  
**Multiple deps:** One `Depends-On:` line per dependency  
**Status:** Emerging de facto standard across tools

### Pattern 2: CrossRepoChange Entity (AI Planning)

**Used by:** Tembo, Claude Code Toolkit (Enigmatica)  
**Mechanism:** A first-class entity that models a change spanning multiple repos  
**Fields:** `id`, `description`, `repoChanges[]`, `status`, `dependencyOrder[]`  
**Key insight:** The dependency order is explicit — this enables automated merge sequencing

### Pattern 3: Dependency Graph + Bottom-Up Propagation

**Used by:** Augment Code, Claude Code Toolkit, Zuul CI  
**Mechanism:** Parse dependency files, build a DAG, then propagate changes from leaves to roots  
**Key insight:** Always update shared libraries first, then dependents, then dependents-of-dependents

### Pattern 4: Speculative Parallel Execution

**Used by:** Zuul CI  
**Mechanism:** Test all changes in parallel assuming dependencies will pass; on failure, retest downstream without the failed change  
**Algorithm:** TCP-inspired window flow control (start at 20, +1 on success, halve on failure)  
**Key insight:** Handles the tension between parallelism and correctness

### Pattern 5: Agent-Agnostic Orchestration

**Used by:** Tembo  
**Mechanism:** Platform sits above individual coding agents; routes tasks to any agent  
**Agents supported:** Claude Code, Codex, Cursor, Amp, OpenCode  
**Key insight:** The coordination layer is durable even as individual agents evolve

### Pattern 6: Git Worktree Isolation

**Used by:** agent-worktree, Worktrunk  
**Mechanism:** Each agent runs in its own `git worktree` — isolated working directory, same repository  
**Key insight:** Solves the conflict problem at the filesystem layer, not through PR coordination

### Pattern 7: Safe Outputs (Guard-Railed Automation)

**Used by:** GitHub Agentic Workflows  
**Mechanism:** Explicit `safe-outputs` in workflow frontmatter that list allowed write operations  
**Key insight:** AI agents run read-only by default; write requires explicit pre-approval per operation type

### Pattern 8: Language-Aware Dependency Injection

**Used by:** depends-on-action  
**Mechanism:** When testing a PR that depends on another PR, inject the dependency's code locally per language convention (Go `replace`, Python `-e`, JS `file:`, Ansible `requirements.yml`)  
**Key insight:** The same cross-repo concept needs different implementation per language/ecosystem

### Pattern 9: PR Templates with Cross-Reference Section

**Used by:** Tembo, Claude Code Toolkit  
**Mechanism:** PR templates include sections for:
- Cross-repo change ID
- Links to related PRs in other repos
- Merge order
- Pre-merge requirements  
**Key insight:** Human-readable metadata in PR bodies is the simplest coordination mechanism

### Pattern 10: Vector DB Code Search for Multi-Repo Impact Analysis

**Used by:** Sweep AI, Augment Code  
**Mechanism:** Embed codebases into vector database, query for semantic similarity across repos to find affected files  
**Key insight:** Before coordinating changes, you need to understand what code references what across repos

---

## Data Model Comparison

| Concept | Tembo | Sweep AI | Claude Code Toolkit | Zuul CI | depends-on-action |
|---|---|---|---|---|---|
| **Workspace** | Implicit (connected repos) | Single repo | `Workspace { name, repos[], conventions }` | `Tenant { projects[] }` | N/A |
| **Change Unit** | `Task` | `FileChangeRequest` | `CrossRepoChange { id, description, repoChanges[], status, depOrder[] }` | `Change` in queue | `PR with Depends-On` |
| **Repo Dependency** | Via task routing | N/A | `RepoConfig.dependencies[]` (names) | Shared change queue | Via Depends-On URL |
| **PR Linkage** | Cross-references in PR body | N/A | Links + merge order in PR body | DAG of Changes | N/A (testing only) |
| **Auth** | Per-repo OAuth | GitHub App | Per-repo tokens | Tenant config | GITHUB_TOKEN |
| **Open Source** | ❌ (self-host option) | ✅ Apache 2.0 | ❌ (reference only) | ✅ Apache 2.0 | ✅ MIT |

---

## Recommendations for Implementation

If building a multi-repo coordination tool for AI coding, the following patterns should be combined:

### 1. Data Model (referencing Claude Code Toolkit + Zuul)
```
Workspace {
  repos: RepoConfig[]          // name, url, defaultBranch, dependencies[]
  conventions: {
    branchPattern, commitFormat, prTemplate
  }
}

CrossRepoChange {
  id: UUID
  description: string
  repoChanges: Map<RepoName, RepoChange>   // branchName, fileDiffs[], commitMessage
  dependencyOrder: RepoName[]               // topological sort of repos
  status: 'planning' | 'in_progress' | 'reviewing' | 'merged' | 'failed'
  prs: Map<RepoName, PRUrl>                 // created PRs
}
```

### 2. PR Linking (referencing Mergify/Zuul convention)
```
Depends-On: https://github.com/org/repo-A/pull/123
Depends-On: https://github.com/org/repo-B/pull/456
Cross-Repo-Change-ID: xyz-789
Merge-Order: repo-A, repo-B, repo-C
```

### 3. Dependency Injection for Testing (referencing depends-on-action)
When testing a PR that depends on another repo's PR:
- **Go:** `go.mod` → `replace` directive
- **Python:** `requirements.txt` → `-e <local path>` or `pyproject.toml` → editable install
- **JS/TS:** `package.json` → `file:<local path>` or workspace protocol
- **Rust:** `Cargo.toml` → `path = "../dependency"`

### 4. Impact Analysis (referencing Sweep AI + Augment)
Before creating coordinated PRs:
1. Scan all repos for references to the changed API/symbol
2. Use vector embeddings for cross-repo semantic search
3. Build dependency graph from package managers
4. Determine topological merge order

### 5. Execution (referencing agent-worktree + Claude Code Toolkit)
For each affected repo:
1. Clone/pull latest
2. Create feature branch per convention
3. Apply changes (from AI-generated diff)
4. Run tests
5. Create PR with cross-repo metadata
6. Tag with `Cross-Repo-Change-ID` label

### 6. Merge Coordination (referencing Zuul CI + Mergify)
1. Process PRs in dependency order
2. After merging upstream dependency:
   - Trigger publish (if library)
   - Wait for new version on package registry
   - Update downstream PRs' dependency references
   - Merge downstream PRs
3. Roll back on failure at any step

---

## Key Open Source Repositories to Reference

| Repo | Stars | License | What to Reference |
|---|---|---|---|
| [sweepai/sweep](https://github.com/sweepai/sweep) | 6K+ | Apache 2.0 | `FileChangeRequest` entity, handler architecture, vector DB code search |
| [zuul/zuul](https://github.com/zuul/zuul) | 3K+ | Apache 2.0 | Cross-project dependency DAG, speculative parallel execution, shared change queue |
| [depends-on/depends-on-action](https://github.com/depends-on/depends-on-action) | 16 | MIT | Language-aware dependency injection for CI testing |
| [nekocode/agent-worktree](https://github.com/nekocode/agent-worktree) | 260 | MIT | Git worktree management, snap mode for AI agent isolation |
| [max-sixty/worktrunk](https://github.com/max-sixty/worktrunk) | Active | ? | CLI for git worktree management designed for AI agents |
| [github/gh-aw](https://github.com/github/gh-aw) | Active | ? | GitHub Agentic Workflows — `.md` workflow format, safe-outputs pattern |

---

*Research conducted 2026-06-05 via DuckDuckGo web search. Content may have evolved since publication.*

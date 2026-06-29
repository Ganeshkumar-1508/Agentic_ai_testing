# Candidate 11: Clean up the project root — 69 entries across 7 categories with no separation

**Strength**: Worth exploring | **Category**: project organization / AI-navigability

---

## Research sources (10)

### Agent harness project root organization patterns

1. **Pantheon (r3moteBee/agent-harness)** — 9 root entries. Clean layout: `backend/` `frontend/` `data/` `docs/` `deploy.sh` `setup_options.sh` `start.sh` `stop.sh` `Makefile`. Every entry has a clear purpose. https://github.com/r3moteBee/pantheon

2. **OpenCode** — Go binary + config. Root has: `cmd/` `internal/` `main.go` `opencode.json`. 4 meaningful entries. https://github.com/opencode-ai/opencode

3. **OpenHands (Agent Canvas)** — Root has: `frontend/` `backend/` `docs/` `Development.md` `README.md` `LICENSE`. ~10 entries. https://github.com/All-Hands-AI/OpenHands

4. **Hermes Agent** — Root has: `agent/` `apps/` `cli/` `gateway/` `tools/` `docs/` `tests/` `README.md`. Clean separation between source (`agent/`, `gateway/`, `tools/`), UI (`apps/`), CLI (`cli/`), docs (`docs/`). https://github.com/NousResearch/hermes-agent

5. **Next.js project conventions** — Standard Next.js root: `src/` `public/` `next.config.ts` `package.json` `tsconfig.json` `.env.local`. Config files stay flat but minimal (~15 entries total). https://nextjs.org/docs

6. **Clean Code / Conway's Law** — "A project root should tell a new developer what this project is in 5 seconds." 69 entries takes much longer than 5 seconds. The root is the project's interface — it should be deep (small interface, much behaviour), not shallow.

7. **Python project conventions** — Standard Python project: `src/` `tests/` `pyproject.toml` `README.md` `LICENSE`. 5 entries. Backend code lives in `src/`, not at root. https://packaging.python.org/

8. **Monorepo best practices** — Google/Turborepo: `packages/` `apps/` `tools/` `docs/` `package.json` `turbo.json`. Source/config/build artifacts separated. Build outputs in `.next/` `dist/` are gitignored. https://turbo.build/repo/docs

9. **Codebase audit — 69 entries, 7 categories** (see below)

10. **CONTEXT.md — AI-navigability** — The project documentation emphasises AI-navigability. A root with 69 mixed entries is not AI-navigable — an AI agent scanning the root can't distinguish source from build artifacts from runtime data from debug scripts.

---

## Codebase evidence

### 69 root entries across 7 categories

| Category | Entries | Count | Notes |
|---|---|---|---|
| **Source code** | `src/` `backend/` | 2 | The actual application code |
| **Configuration** | `.env` `.env.example` `.dockerignore` `.gitignore` `next.config.ts` `tsconfig.json` `postcss.config.mjs` `components.json` `vitest.config.ts` `sandbox.toml` `package.json` `Dockerfile.frontend` `docker-compose.yml` `nginx.conf` `Makefile` `tsconfig.tsbuildinfo` | 17 | Config split across many files |
| **Build artifacts** | `.next/` `node_modules/` `test-results/` `tsconfig.tsbuildinfo` `build*.log` `build*_err.log` `build.stdout.log` `dev.log` | 9 | Build output mixed with source |
| **Documentation** | `CONTEXT.md` `PRODUCT.md` `docs/` | 3 | Good, but minimal |
| **Runtime data** | `data/` `agent_workspace/` `.testai/` `plans/` | 4 | Runtime state mixed with source |
| **External reference** | `reference/` `in_progess/` | 2 | External codebases in repo (note: `in_progess` is a typo) |
| **Ad-hoc debug scripts** | `check_events.py` `check_events2.py` `check_events3.py` `check_orch.py` `check_session.py` `check_tools.py` `submit_f3_smoke.py` `submit_job.py` `test_env_load.py` `test_frontend_api.py` `test_lifespan.py` `analyze_hooks.js` `analyze_hooks.ps1` `nul` `sandbox.html` `logs-wireframe.html` `logs-wireframe-v2.html` `pr_fix_payload.json` `pr_payload.json` `test_payload.json` | 20+ | One-off scripts, debug tools, test payloads — at root level |
| **Other** | `.codegraph/` `.git/` `.github/` `.openclaude/` `.pytest_cache/` `.vscode/` `.openclaude/` `public/` `scripts/` | 9 | IDE, CI, tools |

### Comparison to production agent harnesses

| Project | Root entries | Ratio vs this |
|---|---|---|
| Pantheon | 9 | 7.7× cleaner |
| OpenCode | ~5 | 13.8× cleaner |
| OpenHands | ~10 | 6.9× cleaner |
| Hermes Agent | ~10 | 6.9× cleaner |
| **This project** | **69** | **1× (baseline)** |

### The contraction

- Move ad-hoc scripts (`check_*.py`, `submit_*.py`, `analyze_*.js`, `test_*.py`) into `scripts/` directory
- Move build logs (`build*.log`, `dev.log`) into `logs/` (gitignored)
- Move debug payloads (`pr_payload.json`, `test_payload.json`, `pr_fix_payload.json`) into `scripts/` or `tests/` data
- Move wireframes (`logs-wireframe*.html`, `sandbox.html`) into `docs/`
- Delete `nul` (empty file), fix `in_progess/` typo
- Move `.codegraph/` into `.gitignore` or a config dir
- Result: 69 → ~20 entries. Root tells a clear story: source + config + docs + scripts.

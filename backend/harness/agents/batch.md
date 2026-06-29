---
name: batch
description: Orchestrate large, parallelizable changes across a codebase by decomposing into independent work units
tools:
  - delegate_task
  - todo
  - read
  - write
  - edit
  - codegraph_explore
  - codegraph_search
  - codegraph_node
  - codegraph_callers
  - glob
  - grep
  - bash
  - memory
  - skill_view
---

# Batch: Parallel Work Orchestration

You are orchestrating a large, parallelizable change across this codebase.

## Phase 1: Research and Plan

1. **Understand the scope.** Launch one or more subagents to deeply research what this instruction touches. Find all the files, patterns, and call sites that need to change. Understand the existing conventions so the migration is consistent.

2. **Decompose into independent units.** Break the work into 5-30 self-contained units. Each unit must:
   - Be independently implementable (no shared state with sibling units)
   - Be mergeable on its own without depending on another unit's PR landing first
   - Be roughly uniform in size (split large units, merge trivial ones)

   Scale the count to the actual work: few files → closer to 5; hundreds of files → closer to 30. Prefer per-module slicing over arbitrary file lists.

3. **Determine the verification recipe.** Figure out how a worker can verify its change actually works end-to-end:
   - For API changes: start the dev server, hit the affected endpoints
   - For CLI changes: launch the app, exercise the changed behavior
   - If you cannot find a concrete path, skip e2e and rely on unit tests

4. **Write the plan.** Use `todo` to track each work unit with:
   - A numbered list of work units — for each: a short title, the list of files/directories it covers, and a one-line description
   - The verification recipe workers will follow
   - The exact worker instructions for each unit

## Phase 2: Spawn Workers

Once the plan is ready, spawn one subagent per work unit using delegate_task. Launch them in parallel. For each subagent, the prompt must be fully self-contained.

Each worker prompt must include:
- The overall goal
- This unit's specific task (title, file list, change description)
- The verification recipe
- Clear instructions on what NOT to touch (other units' files)

## Phase 3: Monitor and Collect

- Use todo to track completion of each unit
- If a worker fails, diagnose and retry or re-plan the unit
- Once all workers complete, report a summary of what was changed across all units

Use memory to save the batch plan and results.
---
name: kanban-worker
description: Lifecycle protocol for agents working with kanban boards. Load this skill when you have kanban tools available and need to track progress.
---

# Kanban Worker Protocol

When working with a kanban board, follow this lifecycle:

## 1. Start — Read your task
Call `kanban_show()` to read the current task (title, description, comments, metadata). Understand what needs to be done before starting.

## 2. Work — Use your tools
Use bash, read_file, glob, grep, web_search, and other tools to complete the task. Work inside the workspace directory.

## 3. Heartbeat — Signal progress during long ops
Call `kanban_heartbeat(note="status update here")` every 60 seconds during operations that take longer than a minute. This prevents the task from being claimed by another worker.

## 4. Log progress — Use comments
Call `kanban_comment(task_id, body="what you found or did")` to log findings, decisions, and intermediate results. Comments are visible to the user and other agents.

## 5. Complete — Mark done or blocked
- If done: `kanban_complete(task_id, summary="what was accomplished")`
- If stuck: `kanban_block(task_id, reason="why it's blocked")`

## Rules
- ALWAYS call kanban_show() first to understand the task
- NEVER complete a task you didn't finish — block it instead
- NEVER call kanban_create unless you are an orchestrator spawning subtasks
- Keep kanban_heartbeat calls honest — don't say "still working" when idle

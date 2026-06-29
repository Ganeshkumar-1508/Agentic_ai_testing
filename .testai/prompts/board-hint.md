## CRITICAL: You MUST use kanban tools for every task

1. **kanban_create(title, assignee='coordinator')** — create a task for EACH major step
2. **kanban_heartbeat(note='...')** — call every 60s during long operations
3. **kanban_comment(task_id, body='...')** — log findings and progress
4. **kanban_complete(task_id, summary='...')** — mark tasks done when finished

START by calling kanban_create for your first task. The kanban board is the user's ONLY window into your progress. Do not skip this.

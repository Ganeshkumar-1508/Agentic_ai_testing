CREATE TABLE IF NOT EXISTS provider_configs (
    provider TEXT PRIMARY KEY,
    config TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS interactions (
    id SERIAL PRIMARY KEY,
    user_input TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT,
    project_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    inputs TEXT,
    artifacts TEXT,
    state TEXT,
    error TEXT,
    cost_usd FLOAT DEFAULT 0,
    budget_cap FLOAT DEFAULT 5.00,
    token_count INT DEFAULT 0,
    token_prompt INT DEFAULT 0,
    token_completion INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS job_specs (
    spec_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    prompt TEXT NOT NULL,
    repo_url TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT 'main',
    sha TEXT NOT NULL DEFAULT '',
    tier INTEGER NOT NULL DEFAULT 1,
    capabilities TEXT NOT NULL DEFAULT '[]',
    approval TEXT NOT NULL DEFAULT '{}',
    context TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    latest_run_status TEXT,
    latest_run_cost_usd REAL,
    latest_run_duration_s REAL
);

CREATE INDEX IF NOT EXISTS idx_job_specs_status ON job_specs(status);
CREATE INDEX IF NOT EXISTS idx_job_specs_run_id ON job_specs(run_id);
CREATE INDEX IF NOT EXISTS idx_job_specs_source ON job_specs(source);
CREATE INDEX IF NOT EXISTS idx_job_specs_tier ON job_specs(tier);

CREATE INDEX IF NOT EXISTS idx_job_specs_context_session
    ON job_specs ((context::jsonb->>'session_id'))
    WHERE context::jsonb->>'session_id' IS NOT NULL;

CREATE TABLE IF NOT EXISTS job_checkpoints (
    spec_id TEXT PRIMARY KEY REFERENCES job_specs(spec_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL,
    last_result TEXT NOT NULL DEFAULT '{}',
    paused_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paused_by TEXT NOT NULL DEFAULT '',
    subagent_state TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_job_checkpoints_paused_at ON job_checkpoints(paused_at DESC);

CREATE TABLE IF NOT EXISTS job_comments (
    comment_id TEXT PRIMARY KEY,
    spec_id    TEXT NOT NULL REFERENCES job_specs(spec_id) ON DELETE CASCADE,
    author     TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    kind       TEXT NOT NULL DEFAULT 'comment',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_comments_spec_id ON job_comments(spec_id);
CREATE INDEX IF NOT EXISTS idx_job_comments_created_at ON job_comments(created_at DESC);

CREATE TABLE IF NOT EXISTS job_outputs (
    spec_id       TEXT PRIMARY KEY REFERENCES job_specs(spec_id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT '',
    summary       TEXT NOT NULL DEFAULT '',
    artifacts     TEXT NOT NULL DEFAULT '[]',
    pr_url        TEXT,
    cost_usd      REAL,
    duration_s    REAL,
    completed_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    spec_id TEXT NOT NULL REFERENCES job_specs(spec_id) ON DELETE CASCADE,
    test_files TEXT NOT NULL DEFAULT '[]',
    rationale TEXT NOT NULL DEFAULT '',
    risk_score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending_review',
    reviewer TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_proposals_spec_id ON proposals(spec_id);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'running',
    prompt TEXT,
    state TEXT DEFAULT '{}',
    tool_results TEXT DEFAULT '[]',
    current_step TEXT,
    error TEXT,
    total_tokens INT DEFAULT 0,
    total_cost FLOAT DEFAULT 0.0,
    backend_type TEXT NOT NULL DEFAULT 'local',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mcp_configs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL DEFAULT 'custom',
    server_type TEXT NOT NULL DEFAULT 'user_defined',
    server_url TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    config TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    key_value TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_configs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'webhook',
    events TEXT NOT NULL DEFAULT '["run:completed"]',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline_configs (
    step TEXT PRIMARY KEY,
    provider_model TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trace_events (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    run_id TEXT,
    agent_id TEXT,
    event_type TEXT NOT NULL,
    event_data TEXT,
    console_logs JSONB DEFAULT '[]',
    network_logs JSONB DEFAULT '[]',
    parent_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline_events (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_run ON pipeline_events(run_id, created_at);

CREATE TABLE IF NOT EXISTS test_results (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    run_id TEXT NOT NULL,
    test_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown',
    duration_ms FLOAT DEFAULT 0,
    error TEXT,
    framework TEXT,
    branch TEXT DEFAULT '',
    retry_count INT DEFAULT 0,
    flaky_score FLOAT DEFAULT 0.0,
    is_quarantined BOOLEAN DEFAULT false,
    healed_by_agent BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runner_configs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    language TEXT NOT NULL,
    framework TEXT NOT NULL,
    install_cmd TEXT,
    run_cmd TEXT NOT NULL,
    file_ext TEXT NOT NULL,
    docker_image TEXT,
    bootstrap TEXT DEFAULT '[]',
    config TEXT DEFAULT '{}',
    type TEXT NOT NULL DEFAULT 'builtin',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(language, framework)
);

CREATE TABLE IF NOT EXISTS flaky_tests (
    test_name TEXT NOT NULL,
    run_id TEXT NOT NULL,
    branch TEXT DEFAULT '',
    total_runs INT DEFAULT 0,
    pass_count INT DEFAULT 0,
    fail_count INT DEFAULT 0,
    flaky_score FLOAT DEFAULT 0.0,
    is_quarantined BOOLEAN DEFAULT false,
    last_healed BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (test_name, branch)
);

CREATE TABLE IF NOT EXISTS test_cases (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id TEXT NOT NULL,
    requirement_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    test_type TEXT NOT NULL DEFAULT 'api',
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT DEFAULT 'medium',
    steps TEXT,
    expected_result TEXT,
    test_data TEXT,
    code TEXT,
    code_language TEXT DEFAULT 'python',
    duration_ms INT,
    error_message TEXT,
    stack_trace TEXT,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coverage_reports (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    run_id TEXT,
    language TEXT NOT NULL,
    framework TEXT NOT NULL,
    line_coverage FLOAT DEFAULT 0,
    branch_coverage FLOAT DEFAULT 0,
    total_lines INT DEFAULT 0,
    covered_lines INT DEFAULT 0,
    report_data TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cron_jobs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    schedule_expr TEXT NOT NULL,
    skill TEXT,
    script TEXT,
    enabled BOOLEAN DEFAULT true,
    state TEXT DEFAULT 'scheduled',
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    last_status TEXT,
    max_repeats INT,
    repeat_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quality_gates (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    metric TEXT NOT NULL,
    description TEXT,
    warn_threshold FLOAT NOT NULL DEFAULT 80,
    fail_threshold FLOAT NOT NULL DEFAULT 60,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    description TEXT,
    condition_type TEXT NOT NULL,
    condition_value FLOAT NOT NULL DEFAULT 0,
    condition_direction TEXT DEFAULT 'above',
    action_type TEXT NOT NULL DEFAULT 'webhook',
    action_config TEXT DEFAULT '{}',
    enabled BOOLEAN DEFAULT true,
    silence_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL DEFAULT 'system',
    content TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    model TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quality_metrics (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    run_id TEXT,
    metric_name TEXT NOT NULL,
    metric_value FLOAT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS test_owners (
    test_name TEXT NOT NULL,
    repo_url TEXT NOT NULL,
    team_name TEXT NOT NULL,
    pattern TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (test_name, repo_url)
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    description TEXT,
    control_config TEXT DEFAULT '{}',
    variant_config TEXT DEFAULT '{}',
    target_metric TEXT DEFAULT 'pass_rate',
    status TEXT DEFAULT 'draft',
    runs_completed INT DEFAULT 0,
    total_runs INT DEFAULT 100,
    confidence FLOAT DEFAULT 0,
    winner TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS custom_dashboards (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    description TEXT,
    widgets TEXT DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline_templates (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    requirements TEXT NOT NULL,
    mode TEXT DEFAULT 'auto',
    language TEXT DEFAULT '',
    framework TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    schedule TEXT DEFAULT '',
    repo_url TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS provider_events (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kanban_boards (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    columns JSONB DEFAULT '["backlog","ready","in_progress","review","done","flaky_heat"]',
    config JSONB DEFAULT '{}',
    wip_limits JSONB DEFAULT '{"in_progress": 3}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kanban_tasks (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    board_id TEXT NOT NULL REFERENCES kanban_boards(id) ON DELETE CASCADE,
    parent_task_id TEXT REFERENCES kanban_tasks(id),
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    column_name TEXT NOT NULL DEFAULT 'backlog',
    priority TEXT DEFAULT 'p2',
    tags TEXT DEFAULT '',
    assigned_to TEXT DEFAULT '',

    claim_token TEXT,
    claimed_at TIMESTAMPTZ,
    claim_expires_at TIMESTAMPTZ,
    model_override TEXT,
    toolset_override TEXT,

    pipeline_run_id TEXT,
    coverage_file TEXT,
    flaky_test_name TEXT,

    timebox_seconds INT,
    sla_minutes INT,
    estimate_minutes INT,
    actual_minutes INT,
    template_id TEXT,
    failure_count INT DEFAULT 0,
    sort_order FLOAT DEFAULT 0,

    result_summary TEXT,
    deadline TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kanban_tasks_board ON kanban_tasks(board_id, column_name);
CREATE INDEX IF NOT EXISTS idx_kanban_tasks_assignee ON kanban_tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_kanban_tasks_priority ON kanban_tasks(board_id, priority DESC);
CREATE INDEX IF NOT EXISTS idx_kanban_tasks_coverage ON kanban_tasks(coverage_file) WHERE coverage_file IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_kanban_tasks_flaky ON kanban_tasks(flaky_test_name) WHERE flaky_test_name IS NOT NULL;

CREATE TABLE IF NOT EXISTS kanban_dependencies (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    task_id TEXT NOT NULL REFERENCES kanban_tasks(id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES kanban_tasks(id) ON DELETE CASCADE,
    UNIQUE(task_id, depends_on_task_id)
);
CREATE INDEX IF NOT EXISTS idx_kanban_deps_task ON kanban_dependencies(task_id);
CREATE INDEX IF NOT EXISTS idx_kanban_deps_depends ON kanban_dependencies(depends_on_task_id);

CREATE TABLE IF NOT EXISTS kanban_events (
    id BIGSERIAL PRIMARY KEY,
    board_id TEXT NOT NULL REFERENCES kanban_boards(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES kanban_tasks(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kanban_events_board ON kanban_events(board_id, id);
CREATE INDEX IF NOT EXISTS idx_kanban_events_task ON kanban_events(task_id);

CREATE TABLE IF NOT EXISTS kanban_agent_log (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES kanban_tasks(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kanban_agent_log_task ON kanban_agent_log(task_id, created_at);

CREATE TABLE IF NOT EXISTS memory_entries (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    source TEXT DEFAULT 'auto',
    category TEXT DEFAULT 'general',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_delegations (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    parent_delegation_id BIGINT REFERENCES agent_delegations(id),
    agent_role TEXT NOT NULL DEFAULT 'leaf',
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    tools_used TEXT[] DEFAULT '{}',
    tool_calls_count INT DEFAULT 0,
    duration_ms INT DEFAULT 0,
    error TEXT,
    result_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS pipeline_metrics (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT,
    repo_url TEXT,
    total_tests INT DEFAULT 0,
    passed_tests INT DEFAULT 0,
    failed_tests INT DEFAULT 0,
    pass_rate FLOAT DEFAULT 0,
    duration_seconds FLOAT DEFAULT 0,
    subagent_count INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    total_cost FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sandbox_metrics (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT,
    container_id TEXT,
    container_name TEXT,
    image TEXT,
    status TEXT,
    running BOOLEAN,
    exit_code INT,
    oom_killed BOOLEAN,
    restart_count INT,
    pid INT,
    duration_ms INT DEFAULT 0,
    cpu_shares INT DEFAULT 0,
    memory_limit_bytes BIGINT DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pr_tracker (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    repo_url TEXT,
    repo_provider TEXT NOT NULL DEFAULT 'github',
    pr_number INTEGER NOT NULL,
    title TEXT,
    description TEXT,
    author TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    priority INTEGER DEFAULT 0,
    labels TEXT DEFAULT '[]',
    last_test_status TEXT,
    last_test_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    head_sha TEXT,
    base_sha TEXT,
    source_branch TEXT,
    target_branch TEXT,
    files_changed INTEGER DEFAULT 0,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    reviewers TEXT[] DEFAULT '{}',
    milestone TEXT,
    risk_score DOUBLE PRECISION,
    pr_url TEXT,
    merged_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    commit_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    last_commit_at TIMESTAMPTZ
);
-- Idempotent ALTERs for pre-existing tables that predate the above columns.
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS head_sha TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS base_sha TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS source_branch TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS target_branch TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS files_changed INTEGER DEFAULT 0;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS additions INTEGER DEFAULT 0;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS deletions INTEGER DEFAULT 0;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS reviewers TEXT[] DEFAULT '{}';
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS milestone TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS agent_config TEXT DEFAULT '{}';
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS pr_url TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS merged_at TIMESTAMPTZ;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS commit_count INTEGER DEFAULT 0;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS comments_count INTEGER DEFAULT 0;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS last_commit_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS requirement_links (
    id BIGSERIAL PRIMARY KEY,
    requirement_id TEXT NOT NULL,
    test_case_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stream_events (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT,
    event_type TEXT NOT NULL,
    event_data JSONB DEFAULT '{}',
    parent_id TEXT,
    agent_id TEXT,
    subagent_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- P0 audit fix 2026-06-23: add expires_at + retention_kind for the
-- documented "trajectories=30d, LLM transcripts=7d" TTL policy. The
-- janitor in harness/services/artifact_janitor.py deletes rows
-- past their expires_at daily. Default NULL means "permanent"
-- (e.g. committed test files referenced by kanban_tasks.coverage_file).
ALTER TABLE stream_events ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE stream_events ADD COLUMN IF NOT EXISTS retention_kind TEXT NOT NULL DEFAULT 'transcript';
CREATE INDEX IF NOT EXISTS idx_stream_events_expires ON stream_events(expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    subagent_id TEXT,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    mime_type TEXT DEFAULT 'text/plain',
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_expires ON artifacts(expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS agent_artifacts (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    round_num INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'tool_call',
    tool_name TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
ALTER TABLE agent_artifacts ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_session ON agent_artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_recent ON agent_artifacts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_kind ON agent_artifacts(kind);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_expires ON agent_artifacts(expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS tool_permissions (
    tool_name TEXT PRIMARY KEY,
    level TEXT NOT NULL CHECK (level IN ('allow', 'ask', 'deny')),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_permissions_level ON tool_permissions(level);

-- ---------------------------------------------------------------------------
-- P0 audit additions 2026-06-23
-- ---------------------------------------------------------------------------

-- 4-scope budget (per-subagent / per-phase / per-run / per-user-per-day).
-- The previous SettingsService.upsert_budget wrote to a "budgets" table
-- that did not exist in the schema, so the UI was half-broken. The
-- scope column is the discriminator, name lets the UI show
-- friendly labels like "default (cron)".
CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    scope TEXT NOT NULL CHECK (scope IN ('subagent', 'phase', 'run', 'user_day')),
    name TEXT NOT NULL,
    soft_usd NUMERIC(12, 4) NOT NULL DEFAULT 1.0,
    hard_usd NUMERIC(12, 4) NOT NULL DEFAULT 2.0,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (scope, name)
);
CREATE INDEX IF NOT EXISTS idx_budgets_scope ON budgets(scope);

-- Pipeline hooks (SettingsService.upsert_hook) used to write to a
-- "pipeline_hooks" table that did not exist. The closest match was
-- hooks_index with different column names. Create the right table.
CREATE TABLE IF NOT EXISTS pipeline_hooks (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    event TEXT NOT NULL,
    target_url TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (name, event)
);
CREATE INDEX IF NOT EXISTS idx_pipeline_hooks_event ON pipeline_hooks(event);

-- Optional semantic-search index for the kg. The semantic_search tool
-- checks for the table's existence; if missing it returns "no_embeddings"
-- without breaking. Schema uses pgvector if available, falls back to
-- a JSONB payload column.
CREATE TABLE IF NOT EXISTS kg_embeddings (
    id BIGSERIAL PRIMARY KEY,
    graph_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    embedding JSONB,
    text_preview TEXT,
    model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (graph_id, node_id)
);
CREATE INDEX IF NOT EXISTS idx_kg_embeddings_graph ON kg_embeddings(graph_id);

-- Per-user-per-day budget enforcement (P0 audit §2.6, §2.7). The
-- existing cost/session aggregations group by session_id; this view
-- materialises the per-user rollup for the BudgetSettings UI and the
-- BudgetTracker enforcement path. Until the auth layer threads a
-- user_id onto the chat surface, user_id is NULL and the view
-- returns the global total.
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_token_usage_user_day ON token_usage(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- Trajectory metadata. The JSONL files live on disk
-- (backend/harness/recording.py) but we mirror basic metadata here so
-- the dashboard can list recent trajectories without scanning the FS,
-- and so the artifact janitor can delete the JSONL files when the
-- row's expires_at passes.
CREATE TABLE IF NOT EXISTS session_trajectories (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'recording',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_session_trajectories_session ON session_trajectories(session_id);
CREATE INDEX IF NOT EXISTS idx_session_trajectories_expires ON session_trajectories(expires_at) WHERE expires_at IS NOT NULL;

-- Trace events — the typed OTel-equivalent rows. Add expires_at so
-- the janitor can prune.
ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS retention_kind TEXT NOT NULL DEFAULT 'trace';
CREATE INDEX IF NOT EXISTS idx_trace_events_expires ON trace_events(expires_at) WHERE expires_at IS NOT NULL;

-- ============================================================================
-- Chat surface (Q3, Q5, Q6) — the user-facing chat with the chat LLM.
-- Different shape from the orchestrator's `messages` table: the chat is
-- user/assistant dialog with occasional tool calls, not an agent's
-- tool-call-loop history.
-- ============================================================================

-- A chat thread. 1:1 with a run when auto-created by `submit_job`;
-- ad-hoc (run_id IS NULL) when the user starts a general conversation.
-- `source` distinguishes the creator: 'user' (manual), 'run'
-- (auto-created by submit_job), 'auto' (system), 'github' (a PR
-- comment thread), 'cron' (scheduled).
CREATE TABLE IF NOT EXISTS chat_threads (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title           TEXT NOT NULL DEFAULT 'New conversation',
    run_id          TEXT,
    session_id      TEXT,
    source          TEXT NOT NULL DEFAULT 'user',
    is_pinned       BOOLEAN NOT NULL DEFAULT false,
    is_archived     BOOLEAN NOT NULL DEFAULT false,
    message_count   INTEGER NOT NULL DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_threads_updated ON chat_threads(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_threads_run ON chat_threads(run_id) WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_threads_pinned ON chat_threads(is_pinned, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_threads_archived ON chat_threads(is_archived, updated_at DESC);

-- A single message in a thread. `role` is one of 'user', 'assistant',
-- 'system', 'tool'. `tool_calls` is a JSONB list of
-- {id, name, args} for assistant messages that called tools.
-- `tool_call_id` + `tool_name` + (implied) join on tool_calls[].id
-- gives the 'tool' role row its place. `finish_reason` is one of
-- 'stop', 'tool_calls', 'max_tokens', 'error'. Token + cost fields
-- surface "this response cost $0.002" in the UI.
CREATE TABLE IF NOT EXISTS chat_messages (
    id                TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    thread_id         TEXT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role              TEXT NOT NULL,
    content           TEXT,
    tool_call_id      TEXT,
    tool_calls        JSONB,
    tool_name         TEXT,
    is_error          BOOLEAN NOT NULL DEFAULT false,
    finish_reason     TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost_usd          FLOAT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_tool_call ON chat_messages(tool_call_id) WHERE tool_call_id IS NOT NULL;

-- ============================================================================
-- Agent memory (Q9a) — Mem0-style `add` + `search` over cross-run
-- knowledge.  Replaces the existing filesystem-only `memory_tool.py`
-- with a queryable Postgres index.  The MEMORY.md / USER.md files
-- still live on disk at `~/.testai/memories/<repo-slug>/{MEMORY,USER}.md`;
-- this table is the search index built from those files + L0
-- `agent_artifacts` + L1 `kg_nodes` + L2 `l2_reflection` rows.
--
-- Named `agent_memory` (singular) to avoid clashing with the
-- pre-existing `memory_entries` table (a generic key-value store
-- used by `harness/memory/store.py:PersistentStore`).  The two
-- tables serve different concerns: `memory_entries` is internal
-- KV state; `agent_memory` is the agent's LLM-readable knowledge
-- across runs.
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_memory (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    repo_slug       TEXT NOT NULL,
    source          TEXT NOT NULL,
    target          TEXT NOT NULL DEFAULT 'memory',
    content         TEXT NOT NULL,
    confidence      FLOAT,
    source_kind     TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_memory_repo ON agent_memory(repo_slug, source, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memory_fts ON agent_memory USING GIN (to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_agent_memory_target ON agent_memory(repo_slug, target, created_at DESC);

-- ============================================================================
-- Repo progress (Q9c) — Anthropic two-agent pattern meta. The actual
-- `.testai/feature_list.json` and `.testai/progress.md` files live
-- in the sandbox; this table tracks the per-(repo_url, branch) meta
-- so the dashboard can show "feature_list.json last edited 3 hours
-- ago, 5 of 200 features passing" without scanning the file.
-- ============================================================================
CREATE TABLE IF NOT EXISTS repo_progress (
    repo_url            TEXT NOT NULL,
    branch              TEXT NOT NULL DEFAULT 'main',
    feature_list_path   TEXT NOT NULL DEFAULT '.testai/feature_list.json',
    progress_path       TEXT NOT NULL DEFAULT '.testai/progress.md',
    features_total      INTEGER NOT NULL DEFAULT 0,
    features_passing    INTEGER NOT NULL DEFAULT 0,
    last_edited_at      TIMESTAMPTZ,
    last_run_id         TEXT,
    edit_count          INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_url, branch)
);
CREATE INDEX IF NOT EXISTS idx_repo_progress_updated ON repo_progress(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_repo_progress_edited ON repo_progress(last_edited_at DESC);

-- ============================================================================
-- Sandbox snapshots (Q8) — durable snapshot metadata for the
-- 12-endpoint sandbox visibility surface. The actual Docker image
-- lives in the local image cache; this row is the joinable handle.
-- A janitor deletes after `expires_at`; a 5-snapshot cap per session
-- is enforced in the API layer.
-- ============================================================================
CREATE TABLE IF NOT EXISTS sandbox_snapshots (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id      TEXT NOT NULL,
    docker_image    TEXT NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    size_mb         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sandbox_snapshots_session ON sandbox_snapshots(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sandbox_snapshots_expires ON sandbox_snapshots(expires_at) WHERE expires_at IS NOT NULL;

-- ============================================================================
-- Settings store — general-purpose key-value for UI-saved configuration
-- (escalation policy, data retention, feature flags, etc.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Skill evolution PRs (Q9d) — DROPPED for v1.
-- Decision (2026-06-25): YAGNI. No reference harness (Hermes, OpenClaude,
-- OpenHarness) files curator PRs. Evolved skills land in ~/.testai/skills/
-- and the next session picks them up via the skill tool. If a future
-- revision needs version history, cross-machine sync, or human-review-before-
-- use, see docs/TODO-v1.1.md for re-introduction criteria.
-- ============================================================================
DROP TABLE IF EXISTS skill_evolution_prs CASCADE;

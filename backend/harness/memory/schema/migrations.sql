

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS parent_session_id TEXT REFERENCES sessions(id);
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'api';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS depth INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS agent_role TEXT DEFAULT 'leaf';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS goal TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS model TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS provider TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS estimated_cost_usd REAL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS end_reason TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS workspace_container_id TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS backend_type TEXT NOT NULL DEFAULT 'local';

CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_backend_type ON sessions(backend_type);

CREATE TABLE IF NOT EXISTS session_backend_configs (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    config JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_session_backend_configs_config ON session_backend_configs USING GIN (config);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content JSONB,
    tool_calls JSONB,
    tool_call_id TEXT,
    tool_name TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    token_count INTEGER,
    finish_reason TEXT,
    reasoning TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_fts ON messages USING GIN (to_tsvector('english', COALESCE(content::text, '')));

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    parent_task_id TEXT REFERENCES tasks(id),
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    goal TEXT,
    payload JSONB DEFAULT '{}',
    assigned_agent_type TEXT,
    agent_role TEXT DEFAULT 'leaf',
    depth INTEGER DEFAULT 1,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    result_summary TEXT,
    error TEXT,
    token_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    subagent_id TEXT,
    task_id TEXT REFERENCES tasks(id),
    path TEXT NOT NULL,
    size_bytes INTEGER,
    mime_type TEXT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);

CREATE TABLE IF NOT EXISTS token_usage (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    task_id TEXT REFERENCES tasks(id),
    model TEXT NOT NULL,
    provider TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0,
    actual_cost_usd REAL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_token_usage_session ON token_usage(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_token_usage_model ON token_usage(model, timestamp);

CREATE TABLE IF NOT EXISTS skills_index (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    path TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',  
    category TEXT,
    tags TEXT[] DEFAULT '{}',
    use_count INTEGER DEFAULT 0,
    created_by TEXT DEFAULT 'user',  
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mcp_servers_index (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    command TEXT,
    transport TEXT DEFAULT 'stdio',
    url TEXT,
    enabled BOOLEAN DEFAULT true,
    tool_count INTEGER DEFAULT 0,
    source TEXT DEFAULT 'user',  
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hooks_index (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    hook_type TEXT NOT NULL DEFAULT 'command',
    path TEXT NOT NULL,
    source TEXT DEFAULT 'user',
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, event_type)
);

CREATE TABLE IF NOT EXISTS model_pricing_cache (
    slug TEXT PRIMARY KEY,
    input_per_1m REAL NOT NULL,
    output_per_1m REAL NOT NULL,
    cached_input_per_1m REAL DEFAULT 0,
    context_length INTEGER,
    supports_vision BOOLEAN DEFAULT false,
    supports_reasoning BOOLEAN DEFAULT false,
    supports_tool_calls BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    checkpoint_type TEXT NOT NULL,  
    messages_snapshot JSONB,
    state_snapshot JSONB,
    turn_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON checkpoints(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    task_id TEXT REFERENCES tasks(id),
    proposal_type TEXT NOT NULL,  
    status TEXT NOT NULL DEFAULT 'pending',  
    prompt TEXT,
    context JSONB DEFAULT '{}',
    proposed_action JSONB,
    human_response TEXT,
    responded_by TEXT,
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_approvals_session ON approvals(session_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

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
CREATE INDEX IF NOT EXISTS idx_stream_events_session ON stream_events(session_id, id);
CREATE INDEX IF NOT EXISTS idx_stream_events_type ON stream_events(event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS platform_configs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    platform TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    config TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS delivery_log (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    platform TEXT NOT NULL,
    chat_id TEXT,
    content_preview TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_delivery_log_session ON delivery_log(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS test_case_folders (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    filter_types TEXT[] DEFAULT '{}',
    icon TEXT DEFAULT 'folder',
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE test_cases ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS title TEXT;

CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id TEXT NOT NULL DEFAULT 'default',
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    priority TEXT DEFAULT 'medium',
    source TEXT DEFAULT 'manual',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE test_results ADD COLUMN IF NOT EXISTS defect_id TEXT;
ALTER TABLE test_results ADD COLUMN IF NOT EXISTS defect_url TEXT;

CREATE INDEX IF NOT EXISTS idx_test_cases_requirement ON test_cases(requirement_id);
CREATE INDEX IF NOT EXISTS idx_test_results_defect ON test_results(defect_id);

CREATE TABLE IF NOT EXISTS pr_tracker (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    repo_url TEXT NOT NULL,
    repo_provider TEXT NOT NULL DEFAULT 'github',
    pr_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    head_sha TEXT,
    base_sha TEXT,
    author TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'medium',
    agent_config TEXT DEFAULT '{}',
    labels TEXT[] DEFAULT '{}',
    files_changed INTEGER DEFAULT 0,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    last_test_run_at TIMESTAMPTZ,
    last_test_status TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(repo_url, pr_number)
);

CREATE TABLE IF NOT EXISTS pr_test_runs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    pr_id TEXT NOT NULL REFERENCES pr_tracker(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    test_summary TEXT DEFAULT '{}',
    coverage TEXT DEFAULT '{}',
    quality_score TEXT DEFAULT '{}',
    triggered_by TEXT DEFAULT 'auto',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_tracker_status ON pr_tracker(status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_pr_test_runs_pr ON pr_test_runs(pr_id, created_at DESC);

ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS risk_score REAL DEFAULT 0;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS source_branch TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS target_branch TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS reviewers TEXT[] DEFAULT '{}';
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS milestone TEXT;
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS pipeline_run_id TEXT;

ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS auto_fix_enabled BOOLEAN DEFAULT false;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS auto_fix_max_cycles INTEGER DEFAULT 5;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS last_logaf_score REAL;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS total_fix_cycles INTEGER DEFAULT 0;

ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS cycle_number INTEGER DEFAULT 1;
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS failure_tier TEXT;
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS logaf_score REAL;
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS failures_fixed INTEGER DEFAULT 0;
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS failures_remaining INTEGER DEFAULT 0;
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS fix_diff TEXT;
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS commit_sha TEXT;
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS error_classification TEXT DEFAULT '{}';
ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS notification_sent BOOLEAN DEFAULT false;

CREATE TABLE IF NOT EXISTS test_impact_map (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    file_path TEXT NOT NULL,
    test_name TEXT NOT NULL,
    repo_url TEXT NOT NULL DEFAULT '',
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(file_path, test_name, repo_url)
);
CREATE INDEX IF NOT EXISTS idx_impact_file ON test_impact_map(file_path, repo_url);

CREATE TABLE IF NOT EXISTS execution_shards (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    run_id TEXT NOT NULL,
    shard_index INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    container_id TEXT,
    test_count INTEGER DEFAULT 0,
    passed_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS visual_baselines (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    test_name TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT 'main',
    viewport TEXT DEFAULT '1280x720',
    baseline_path TEXT NOT NULL,
    baseline_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(test_name, branch, viewport)
);

CREATE TABLE IF NOT EXISTS visual_diffs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    run_id TEXT NOT NULL,
    test_name TEXT NOT NULL,
    baseline_id TEXT REFERENCES visual_baselines(id),
    diff_pixels INTEGER DEFAULT 0,
    diff_percent REAL DEFAULT 0,
    diff_image_path TEXT,
    passed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS load_test_runs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT,
    spec_url TEXT,
    test_type TEXT DEFAULT 'stress',
    virtual_users INTEGER DEFAULT 10,
    duration_seconds INTEGER DEFAULT 60,
    p50_ms REAL,
    p95_ms REAL,
    p99_ms REAL,
    error_rate REAL,
    throughput_rps REAL,
    status TEXT DEFAULT 'pending',
    raw_results TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS healing_log (
    id BIGSERIAL PRIMARY KEY,
    test_name TEXT NOT NULL,
    old_locator TEXT NOT NULL,
    new_locator TEXT,
    strategy TEXT,
    confidence REAL,
    screenshot_before TEXT,
    screenshot_after TEXT,
    passed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS digest_configs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    platform TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    schedule TEXT DEFAULT '0 8 * * 1-5',
    filters TEXT DEFAULT '{}',
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS notification_channels TEXT DEFAULT '[]';
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS last_notification_sent_at TIMESTAMPTZ;

ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS agent_config TEXT DEFAULT '{}';
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS pr_url TEXT;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS merged_at TIMESTAMPTZ;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS commit_count INTEGER DEFAULT 0;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS comments_count INTEGER DEFAULT 0;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS last_commit_at TIMESTAMPTZ;

ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS impact_analysis_enabled BOOLEAN DEFAULT false;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS parallel_execution_enabled BOOLEAN DEFAULT false;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS visual_testing_enabled BOOLEAN DEFAULT false;
ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS load_testing_enabled BOOLEAN DEFAULT false;

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;

ALTER TABLE provider_configs ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'project';
ALTER TABLE mcp_configs ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'project';

ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS agent_delegations (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    parent_delegation_id BIGINT REFERENCES agent_delegations(id),
    agent_role TEXT NOT NULL DEFAULT 'leaf',
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    tools_used TEXT[] DEFAULT '{}',
    tool_calls_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    error TEXT,
    result_summary TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_agent_delegations_session ON agent_delegations(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_delegations_parent ON agent_delegations(parent_delegation_id);

CREATE TABLE IF NOT EXISTS pipeline_metrics (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    repo_url TEXT,
    total_tests INTEGER DEFAULT 0,
    passed_tests INTEGER DEFAULT 0,
    failed_tests INTEGER DEFAULT 0,
    pass_rate REAL DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost REAL DEFAULT 0,
    subagent_count INTEGER DEFAULT 0,
    tool_calls_total INTEGER DEFAULT 0,
    duration_seconds INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pipeline_metrics_session ON pipeline_metrics(session_id);

CREATE TABLE IF NOT EXISTS sandbox_metrics (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    container_id TEXT,
    container_name TEXT,
    image TEXT,
    execution_id TEXT,
    command TEXT,
    exit_code INTEGER DEFAULT 0,
    status TEXT DEFAULT 'unknown',
    running BOOLEAN DEFAULT false,
    oom_killed BOOLEAN DEFAULT false,
    restart_count INTEGER DEFAULT 0,
    pid INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    cpu_shares INTEGER DEFAULT 0,
    memory_limit_bytes BIGINT DEFAULT 0,
    memory_usage_bytes BIGINT DEFAULT 0,
    network_rx_bytes BIGINT DEFAULT 0,
    network_tx_bytes BIGINT DEFAULT 0,
    block_read_bytes BIGINT DEFAULT 0,
    block_write_bytes BIGINT DEFAULT 0,
    pids_current INTEGER DEFAULT 0,
    stdout_size INTEGER DEFAULT 0,
    stderr_size INTEGER DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sandbox_metrics_session ON sandbox_metrics(session_id);

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS cost_usd FLOAT DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS budget_cap FLOAT DEFAULT 5.00;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS token_count INT DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS token_prompt INT DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS token_completion INT DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS impact_summary TEXT;

CREATE TABLE IF NOT EXISTS env_vars (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id TEXT NOT NULL DEFAULT 'default',
    key TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    is_secret BOOLEAN DEFAULT false,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, key)
);

CREATE TABLE IF NOT EXISTS notification_prefs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    channel TEXT NOT NULL DEFAULT 'email',
    enabled BOOLEAN DEFAULT true,
    events TEXT DEFAULT '["run:completed","run:failed","heal:escalated"]',
    target TEXT DEFAULT '',
    project_id TEXT DEFAULT '*',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS saved_filters (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    filter_data TEXT DEFAULT '{}',
    icon TEXT DEFAULT 'Filter',
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feature_flags (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT DEFAULT '',
    enabled BOOLEAN DEFAULT false,
    rollout_percent INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS integration_configs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    platform TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    config JSONB DEFAULT '{}',
    project_mappings JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_integration_platform ON integration_configs(platform);

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

CREATE TABLE IF NOT EXISTS kanban_agent_log (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES kanban_tasks(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kanban_agent_log_task ON kanban_agent_log(task_id, created_at);

CREATE TABLE IF NOT EXISTS agent_definitions (
    role TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    description TEXT DEFAULT '',
    system_prompt TEXT DEFAULT '',
    allowed_tools TEXT[] DEFAULT '{}',
    allowed_skills TEXT[] DEFAULT '{}',
    model_primary TEXT DEFAULT '',
    model_fallback TEXT DEFAULT '',
    delegation_depth INTEGER DEFAULT 1,
    delegation_role TEXT DEFAULT 'leaf',
    triggers TEXT[] DEFAULT '{}',
    bash_constraints JSONB DEFAULT '{}',
    output_contract TEXT DEFAULT '',
    source TEXT NOT NULL DEFAULT 'builtin',
    source_path TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kg_nodes (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    file_type TEXT DEFAULT 'code',
    source_file TEXT DEFAULT '',
    properties JSONB DEFAULT '{}',
    run_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_label ON kg_nodes(label);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_file ON kg_nodes(source_file);

CREATE TABLE IF NOT EXISTS kg_edges (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    confidence TEXT DEFAULT 'EXTRACTED',
    confidence_score REAL DEFAULT 1.0,
    source_file TEXT DEFAULT '',
    run_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, target_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_relation ON kg_edges(relation);

CREATE TABLE IF NOT EXISTS semantic_routes (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    route_name TEXT NOT NULL,
    route_type TEXT NOT NULL DEFAULT 'agent',  
    target_id TEXT NOT NULL,
    examples TEXT[] DEFAULT '{}',  
    embedding JSONB,  
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_semantic_routes_name ON semantic_routes(route_name);
CREATE INDEX IF NOT EXISTS idx_semantic_routes_type ON semantic_routes(route_type);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    channel TEXT NOT NULL,
    recipient TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    body TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    error TEXT,
    source TEXT DEFAULT 'agent',
    run_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    delivered_at TIMESTAMPTZ
);

ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT false;
ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS review_status TEXT DEFAULT NULL;
ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS review_notes TEXT DEFAULT NULL;
ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS reviewed_by TEXT DEFAULT NULL;
ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS repo_url TEXT DEFAULT '';

ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS sprint TEXT DEFAULT '';

ALTER TABLE cron_jobs ADD COLUMN IF NOT EXISTS repo_url TEXT DEFAULT '';
ALTER TABLE cron_jobs ADD COLUMN IF NOT EXISTS branch TEXT DEFAULT '';

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS session_id TEXT;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS test_count INTEGER DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS passed_count INTEGER DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS failed_count INTEGER DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS skipped_count INTEGER DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS duration DOUBLE PRECISION DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS total_tokens INTEGER DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS estimated_cost_usd REAL DEFAULT 0;

ALTER TABLE test_cases ADD COLUMN IF NOT EXISTS source TEXT DEFAULT '';

CREATE TABLE IF NOT EXISTS provider_definitions (
    name TEXT PRIMARY KEY,
    api_mode TEXT NOT NULL DEFAULT 'chat_completions',
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    signup_url TEXT DEFAULT '',
    env_vars TEXT DEFAULT '',         
    base_url TEXT DEFAULT '',
    auth_type TEXT NOT NULL DEFAULT 'api_key',
    fallback_models TEXT DEFAULT '',  
    default_headers TEXT DEFAULT '{}',
    is_builtin BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sandbox_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO sandbox_config (key, value) VALUES
    ('default_timeout', '60'),
    ('max_parallel', '4'),
    ('memory_limit_mb', '512'),
    ('cpu_limit', '1.0'),
    ('docker_image', 'nikolaik/python-nodejs:python3.11-nodejs20'),
    ('cleanup_idle_minutes', '30'),
    ('network_enabled', 'true')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message_reactions (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    reaction_type TEXT NOT NULL CHECK (reaction_type IN ('up', 'down')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, message_id)
);

CREATE TABLE IF NOT EXISTS approval_queue (
    id SERIAL PRIMARY KEY,
    tool_call_id TEXT,
    tool_name TEXT,
    args JSONB,
    session_id TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE agent_delegations ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE agent_delegations ADD COLUMN IF NOT EXISTS input_tokens INTEGER DEFAULT 0;
ALTER TABLE agent_delegations ADD COLUMN IF NOT EXISTS output_tokens INTEGER DEFAULT 0;

ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS agent_type TEXT DEFAULT 'general-purpose';
ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    lead_subagent_id TEXT,
    lead_session_id TEXT,
    goal TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',  
    created_at TIMESTAMPTZ DEFAULT NOW(),
    dissolved_at TIMESTAMPTZ,
    config JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_teams_status ON teams(status);
CREATE INDEX IF NOT EXISTS idx_teams_lead_session ON teams(lead_session_id);

CREATE TABLE IF NOT EXISTS team_members (
    team_id TEXT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    subagent_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',  
    role_name TEXT DEFAULT '',           
    status TEXT NOT NULL DEFAULT 'active',  
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    left_at TIMESTAMPTZ,
    PRIMARY KEY (team_id, subagent_id)
);
CREATE INDEX IF NOT EXISTS idx_team_members_subagent ON team_members(subagent_id);
CREATE INDEX IF NOT EXISTS idx_team_members_status ON team_members(team_id, status);

CREATE TABLE IF NOT EXISTS team_messages (
    id BIGSERIAL PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    from_subagent_id TEXT,
    to_subagent_id TEXT,         
    content TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'message',  
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_team_messages_team ON team_messages(team_id, created_at);
CREATE INDEX IF NOT EXISTS idx_team_messages_recipient
    ON team_messages(team_id, to_subagent_id, created_at)
    WHERE to_subagent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kanban_events_task_comments ON kanban_events(task_id, event_type);

-- ============================================================================
-- P0 audit additions 2026-06-23 (see docs/2026-06-23-orchestrator-audit.md)
-- ============================================================================
-- database.py runs these statements at startup (safety net for fresh installs).
-- It strips -- comment lines before splitting on ; to avoid false splits.
-- Do not put ; inside string literals in SQL statements.

-- TTL columns for documented retention policy:
--   committed test files = permanent, trajectories = 30d, LLM transcripts = 7d
ALTER TABLE stream_events   ADD COLUMN IF NOT EXISTS expires_at    TIMESTAMPTZ;
ALTER TABLE stream_events   ADD COLUMN IF NOT EXISTS retention_kind TEXT NOT NULL DEFAULT 'transcript';
ALTER TABLE artifacts      ADD COLUMN IF NOT EXISTS expires_at    TIMESTAMPTZ;
ALTER TABLE agent_artifacts ADD COLUMN IF NOT EXISTS expires_at   TIMESTAMPTZ;
ALTER TABLE trace_events   ADD COLUMN IF NOT EXISTS expires_at    TIMESTAMPTZ;
ALTER TABLE trace_events   ADD COLUMN IF NOT EXISTS retention_kind TEXT NOT NULL DEFAULT 'trace';

CREATE INDEX IF NOT EXISTS idx_stream_events_expires    ON stream_events(expires_at)    WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_artifacts_expires        ON artifacts(expires_at)         WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_expires  ON agent_artifacts(expires_at)   WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_trace_events_expires     ON trace_events(expires_at)      WHERE expires_at IS NOT NULL;

-- Per-user-per-day budget + per-user columns
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE sessions    ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_token_usage_user_day ON token_usage(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sessions_user        ON sessions(user_id);

-- 4-scope budget (SettingsService.upsert_budget target table)
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

-- Pipeline hooks (SettingsService.upsert_hook target table)
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

-- Optional semantic-search index for the knowledge graph
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

-- Trajectory metadata mirror
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

-- ============================================================================
-- SettingsService table aliases 2026-06-23
-- ============================================================================
CREATE TABLE IF NOT EXISTS webhook_channels (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'webhook',
    events JSONB DEFAULT '[]'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    prompt TEXT DEFAULT '',
    tier INTEGER DEFAULT 2,
    skills JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS providers (
    provider TEXT PRIMARY KEY,
    base_url TEXT DEFAULT '',
    model TEXT DEFAULT '',
    api_mode TEXT DEFAULT 'openai',
    enabled BOOLEAN DEFAULT true,
    options JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'webhook',
    events JSONB DEFAULT '[]'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    prompt TEXT DEFAULT '',
    tier INTEGER DEFAULT 2,
    skills JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS pipeline_config (
    id BIGSERIAL PRIMARY KEY,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS notification_delivery (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    platform TEXT NOT NULL UNIQUE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS notification_preferences (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    channel TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    events JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- ============================================================================
-- SettingsService table fix 2026-06-23
-- The SettingsService CRUD methods reference table names that
-- differ from the canonical schema:
--   providers          -> settings_service.get_providers / upsert_provider
--   webhooks           -> settings_service.get_webhooks / etc
--   pipeline_config    -> settings_service.get_pipeline_config
--   notification_delivery -> settings_service.get_platforms
--   notification_preferences -> settings_service.get_notification_prefs
-- These CREATE the tables SettingsService expects so the UI
-- endpoints work. (The real tables `provider_configs`,
-- `webhook_configs`, `pipeline_configs`, `platform_configs`,
-- `notification_prefs` are the canonical store; a future
-- migration should reconcile.)
-- ============================================================================

CREATE TABLE IF NOT EXISTS providers (
    provider TEXT PRIMARY KEY,
    base_url TEXT DEFAULT '',
    model TEXT DEFAULT '',
    api_mode TEXT DEFAULT 'openai',
    enabled BOOLEAN DEFAULT true,
    options JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'webhook',
    events JSONB DEFAULT '[]'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline_config (
    id BIGSERIAL PRIMARY KEY,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notification_delivery (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    platform TEXT NOT NULL UNIQUE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notification_preferences (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    channel TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    events JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- SettingsService table aliases (continued) 2026-06-23
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_memories (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    content TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS test_impact (
    id BIGSERIAL PRIMARY KEY,
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    test_name TEXT,
    file_path TEXT,
    impact_score FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS regression_data (
    id BIGSERIAL PRIMARY KEY,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    test_name TEXT,
    branch TEXT,
    status TEXT DEFAULT 'open',
    details TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent versioning: snapshots of agent config on every save
CREATE TABLE IF NOT EXISTS agent_versions (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    version INT NOT NULL,
    snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    message TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_versions_name ON agent_versions(agent_name, version DESC);

# Hermes, OpenCode, OpenClaw: Parallel Agent Spawning Comparison

**Date**: 2026-06-18  
**Purpose**: Compare how production-grade open-source agent frameworks handle parallel agent spawning

---

## Executive Summary

All three frameworks (Hermes, OpenCode, OpenClaw) implement parallel agent spawning with **different architectural approaches**:

- **Hermes**: Thread-based parallelism with `delegate_task`, heartbeat monitoring, and sophisticated timeout/stale detection
- **OpenCode**: Session-based subagents with primary/secondary agent hierarchy, configuration-driven parallelism
- **OpenClaw**: Push-based completion model with `sessions_spawn`, isolated/fork context modes, and retry logic

**TestAI's current implementation** is closest to Hermes (both use `delegate_task`), but lacks Hermes's heartbeat monitoring and stale detection.

---

## Hermes Agent Framework

### Architecture

**Core Mechanism**: `delegate_task` tool with thread-based parallelism

**Key Components**:
- **ThreadPoolExecutor**: Each subagent runs in its own thread with timeout management
- **Heartbeat System**: Periodic activity propagation to prevent gateway timeouts
- **Stale Detection**: Monitors tool/iteration progress to detect hung subagents
- **Credential Pooling**: Subagents can lease credentials from parent's pool

### Spawning Pattern

```python
# Hermes delegate_task implementation
delegate_task(
    tasks=[
        {"goal": "Task 1", "context": "...", "toolsets": ["terminal", "file"]},
        {"goal": "Task 2", "context": "...", "toolsets": ["terminal", "file"]},
        {"goal": "Task 3", "context": "...", "toolsets": ["terminal", "file"]},
    ]
)
```

**Parallel Execution**:
- Default: 3 concurrent subagents (configurable via `delegation.max_concurrent_children`)
- Each subagent gets its own conversation, terminal session, and toolset
- Only final summary returns to parent — intermediate tool calls don't pollute parent context

### Heartbeat Mechanism

**Problem Solved**: Gateway inactivity timeout fires when parent is blocked waiting for subagents.

**Solution**:
```python
def _heartbeat_loop():
    while not _heartbeat_stop.wait(_HEARTBEAT_INTERVAL):
        # Pull child activity summary
        child_summary = child.get_activity_summary()
        child_tool = child_summary.get("current_tool")
        child_iter = child_summary.get("api_call_count", 0)
        
        # Stale detection: count cycles where neither iteration
        # count nor current_tool advances
        iter_advanced = child_iter > _last_seen_iter[0]
        tool_changed = child_tool != _last_seen_tool[0]
        
        if iter_advanced or tool_changed:
            _stale_count[0] = 0
        else:
            _stale_count[0] += 1
        
        # Pick threshold based on whether child is in a tool call
        stale_limit = (
            _HEARTBEAT_STALE_CYCLES_IN_TOOL
            if child_tool
            else _HEARTBEAT_STALE_CYCLES_IDLE
        )
        
        if _stale_count[0] >= stale_limit:
            break  # stop touching parent, let gateway timeout fire
        
        # Touch parent activity timestamp
        touch(desc)
```

**Key Features**:
- **Idle Threshold**: Tight threshold for truly wedged subagents
- **In-Tool Threshold**: Higher threshold for legitimately slow tools (terminal commands, web fetches)
- **Stale Detection**: Counts cycles without progress to detect hung subagents
- **Graceful Degradation**: Stops heartbeat when stale, allows gateway timeout to fire

### Timeout Management

**Hard Timeout**: Each subagent has a configurable timeout to prevent indefinite blocking.

**Implementation**:
```python
_timeout_executor = ThreadPoolExecutor(max_workers=1)

def _run_with_thread_capture():
    _worker_thread_holder["t"] = threading.current_thread()
    return child.run_conversation(user_message=goal, task_id=child_task_id)

_child_future = _timeout_executor.submit(_run_with_thread_capture)
try:
    result = _child_future.result(timeout=child_timeout)
except FuturesTimeoutError:
    # Signal child to stop
    if hasattr(child, "interrupt"):
        child.interrupt()
    
    # Dump diagnostic if 0 API calls (stuck before first LLM call)
    if child_api_calls == 0:
        diagnostic_path = _dump_subagent_timeout_diagnostic(...)
```

**Diagnostic Features**:
- **0-API-Call Timeout**: Detects subagents stuck before first LLM request
- **Thread Stack Dump**: Captures Python stack of hung worker thread
- **Activity Summary**: Reports last tool, iteration count, duration

### Toolset Isolation

**Default Toolsets**:
- `["terminal", "file"]` — Shell access + file operations
- `["web"]` — Web search + extraction only
- `["terminal", "file", "web"]` — Full access except messaging
- `["file"]` — Read-only file access

**Blocked Tools for Leaf Subagents**:
- `delegate_task` — Prevents unbounded nesting (opt-in for orchestrator role)
- `clarify` — Subagents can't prompt user
- `memory` — Subagents don't persist to long-term memory
- `send_message` — Subagents don't send external messages

### Result Collection

**Synchronous Mode** (default):
- Parent blocks until all subagents complete
- Returns consolidated summary to parent
- Parent synthesizes results

**Asynchronous Mode** (background):
- Returns task IDs immediately
- Parent can poll for completion
- Use case: Long-running tasks that shouldn't block chat

### Configuration

```yaml
# config.yaml
delegation:
  max_concurrent_children: 3  # Default parallelism
  max_spawn_depth: 5  # Max nesting depth
  child_timeout: 300  # Seconds per subagent
  subagent_auto_approve: false  # Require approval for dangerous commands
```

---

## OpenCode

### Architecture

**Core Mechanism**: Primary agents and subagents with session-based isolation

**Key Components**:
- **Primary Agents**: Main assistants (Build, Plan) that handle direct user interaction
- **Subagents**: Specialized assistants (General, Explore, Scout) invoked by primary agents
- **Session Isolation**: Each subagent runs in its own session with separate context

### Agent Types

**Primary Agents**:
- **Build** (default): Full tool access, standard development work
- **Plan**: Restricted permissions (edit: deny, bash: deny), analysis and planning only

**Subagents**:
- **General**: Full tool access (except todo), multi-step tasks, parallel work units
- **Explore**: Read-only, fast codebase exploration, cannot modify files
- **Scout**: Read-only, external docs and dependency research, clones repos into managed cache

### Spawning Pattern

**Automatic Spawning**:
```typescript
// Primary agent automatically spawns subagent based on task
@general help me search for this function
```

**Manual Spawning**:
```typescript
// User invokes subagent directly
@explore find all usages of this function
@scout research this library's API
```

**Parallel Execution**:
- Primary agents can invoke multiple subagents concurrently
- Each subagent runs in isolated session
- Results returned to primary agent for synthesis

### Configuration

**JSON Configuration**:
```json
{
  "agent": {
    "build": {
      "mode": "primary",
      "model": "anthropic/claude-sonnet-4-20250514",
      "prompt": "{file:./prompts/build.txt}",
      "permission": {
        "edit": "allow",
        "bash": "allow"
      }
    },
    "explore": {
      "mode": "subagent",
      "model": "anthropic/claude-haiku-4-20250514",
      "description": "Fast, read-only agent for exploring codebases",
      "permission": {
        "edit": "deny",
        "bash": "deny"
      }
    }
  }
}
```

**Markdown Configuration**:
```markdown
<!-- ~/.config/opencode/agents/review.md -->
---
description: Reviews code for quality and best practices
mode: subagent
model: anthropic/claude-sonnet-4-20250514
temperature: 0.1
permission:
  edit: deny
  bash: deny
---

You are in code review mode. Focus on:
- Code quality and best practices
- Potential bugs and edge cases
- Performance implications
- Security considerations

Provide constructive feedback without making direct changes.
```

### Session Navigation

**Parent-Child Navigation**:
- `session_child_first` (default: `<Leader>+Down`): Enter first child session
- `session_child_cycle` (default: `Right`): Cycle to next child session
- `session_child_cycle_reverse` (default: `Left`): Cycle to previous child session
- `session_parent` (default: `Up`): Return to parent session

**Use Case**: Switch between main conversation and specialized subagent work

### Context Management

**Compaction Agent**:
- Hidden system agent that compacts long context into smaller summary
- Runs automatically when context window fills up
- Not selectable in UI

**Title Agent**:
- Hidden system agent that generates short session titles
- Runs automatically after first interaction
- Not selectable in UI

**Summary Agent**:
- Hidden system agent that creates session summaries
- Runs automatically on session end
- Not selectable in UI

### Parallel Execution Pattern

**Multi-File Refactoring**:
```typescript
// Primary agent spawns multiple subagents for parallel work
@general refactor src/handlers/users.py to use new response format
@general refactor src/handlers/auth.py to use new response format
@general refactor src/handlers/billing.py to use new response format
```

**Research Pattern**:
```typescript
// Primary agent spawns multiple explore subagents
@explore find all usages of deprecated API
@explore find all test files for this module
@explore find all imports of this function
```

### Key Differences from Hermes

| Feature | Hermes | OpenCode |
|---------|--------|----------|
| **Parallelism Model** | Thread-based with `delegate_task` | Session-based with subagent invocation |
| **Heartbeat Monitoring** | ✅ Yes — prevents gateway timeouts | ❌ No — relies on session timeout |
| **Stale Detection** | ✅ Yes — monitors tool/iteration progress | ❌ No — no progress monitoring |
| **Timeout Management** | ✅ Hard timeout per subagent | ❌ No explicit timeout |
| **Toolset Isolation** | ✅ Explicit toolset selection | ⚠️ Permission-based (allow/deny/ask) |
| **Context Isolation** | ✅ Fresh context per subagent | ✅ Session-based isolation |
| **Result Collection** | ✅ Synchronous (blocks until complete) | ⚠️ Asynchronous (session-based) |
| **Nesting Control** | ✅ Configurable max depth | ❌ No explicit nesting control |
| **Credential Pooling** | ✅ Subagents lease from parent pool | ❌ No credential sharing |

---

## OpenClaw

### Architecture

**Core Mechanism**: `sessions_spawn` tool with push-based completion model

**Key Components**:
- **Background Sub-Agents**: Spawned from existing agent run, run in own session
- **Push-Based Completion**: Sub-agent announces result back to requester when done
- **Context Modes**: Isolated (fresh context) vs Fork (branched from parent)
- **Completion Delivery**: Sophisticated retry logic with exponential backoff

### Spawning Pattern

```typescript
// OpenClaw sessions_spawn implementation
sessions_spawn({
  task: "Research WebAssembly outside the browser",
  context: "isolated",  // or "fork"
  model: "anthropic/claude-haiku-4-20250514",  // optional
  thinking: "low",  // optional
})
```

**Session Isolation**:
- Each sub-agent runs in `agent:<agentId>:subagent:<uuid>` session
- Tracked as background task
- Completion announced via internal parent-session event

### Context Modes

**Isolated Mode** (default):
- Fresh child transcript
- Lower token usage
- Use case: Independent research, implementation, slow tool work

**Fork Mode**:
- Branches requester transcript into child session
- Child has access to parent's conversation history
- Use case: Context-sensitive delegation, work depending on prior tool results

**Recommendation**: Use `isolated` by default, `fork` sparingly for context-sensitive work

### Push-Based Completion

**Non-Blocking Spawn**:
```typescript
// sessions_spawn returns immediately with run ID
const runId = sessions_spawn({ task: "..." });

// Parent continues working
// ...

// Sub-agent completion arrives as internal event
// Parent decides whether to surface to user
```

**Completion Delivery**:
1. Sub-agent finishes, generates result
2. OpenClaw attempts to wake/steer active requester run
3. If requester can't be woken, falls back to requester-agent handoff
4. If handoff fails, retries with exponential backoff
5. Final give-up if all delivery attempts fail

**Idempotency**:
- Completion handoff uses stable idempotency key
- Prevents duplicate delivery on retry
- Ensures exactly-once delivery semantics

### Completion Handoff Metadata

**Runtime-Generated Context** (not user-authored):
- **Result**: Latest visible assistant reply from child
- **Status**: `completed` / `failed` / `timed out` / `unknown`
- **Stats**: Compact runtime/token statistics
- **Review Instruction**: Tells requester to verify result before deciding
- **Follow-Up Guidance**: Tells requester to continue task or record follow-up
- **Final-Update Instruction**: For no-more-action path, written in normal assistant voice

**Key Principle**: Child output is evidence for requester to synthesize, not user-authored instruction text

### Tool Isolation

**Default Restrictions**:
- Sub-agents do NOT get `message` tool by default
- Sub-agents return plain assistant text to parent
- Human-visible replies owned by parent's normal delivery policy

**Rationale**: Prevents sub-agents from directly messaging users, ensures parent controls communication

### Thread Binding

**Thread-Supporting Channels**:
```typescript
// Persistent thread-bound sessions
sessions_spawn({
  task: "...",
  thread: true,
  mode: "session"  // persistent thread binding
})
```

**Non-Thread Channels**:
```typescript
// Use run mode instead
sessions_spawn({
  task: "...",
  mode: "run"  // ephemeral run
})
```

**Commands**:
- `/focus <subagent-label>`: Focus on subagent thread
- `/unfocus`: Return to parent thread
- `/agents/session idle <duration>`: Set idle timeout
- `/session max-age <duration>`: Set max session age

### ACP Runtime Integration

**External Harness Support**:
```typescript
// Spawn Claude Code, Gemini CLI, OpenCode, or Codex ACP
sessions_spawn({
  task: "...",
  runtime: "acp",
  harness: "claude-code"  // or "gemini-cli", "opencode", "codex"
})
```

**Use Case**: Leverage external agent harnesses as sub-agents

**Restrictions**:
- ACP runtime hidden until ACP enabled
- Requester must not be sandboxed
- Backend plugin (e.g., `acpx`) must be loaded

### Monitoring

**Slash Commands**:
```bash
/subagents list                    # List sub-agent runs
/subagents log <id|#> [limit]      # View sub-agent log
/subagents info <id|#>             # View run metadata
```

**Metadata**:
- Status, timestamps, session ID
- Transcript path (for raw full transcript)
- Cleanup status

### Key Differences from Hermes

| Feature | Hermes | OpenClaw |
|---------|--------|----------|
| **Parallelism Model** | Thread-based with `delegate_task` | Session-based with `sessions_spawn` |
| **Completion Model** | Synchronous (blocks until complete) | Push-based (non-blocking, event-driven) |
| **Heartbeat Monitoring** | ✅ Yes — prevents gateway timeouts | ❌ No — relies on session timeout |
| **Stale Detection** | ✅ Yes — monitors tool/iteration progress | ❌ No — no progress monitoring |
| **Timeout Management** | ✅ Hard timeout per subagent | ❌ No explicit timeout |
| **Context Modes** | ✅ Fresh context only | ✅ Isolated + Fork modes |
| **Completion Delivery** | ✅ Direct return to parent | ⚠️ Retry logic with exponential backoff |
| **Thread Binding** | ❌ No — thread-based only | ✅ Yes — persistent thread sessions |
| **ACP Integration** | ❌ No — Hermes-only subagents | ✅ Yes — external harness support |
| **Tool Isolation** | ✅ Explicit toolset selection | ⚠️ Tool policy-based (no message tool) |

---

## Comparative Analysis

### Parallelism Models

| Framework | Model | Blocking? | Concurrency Control |
|-----------|-------|-----------|---------------------|
| **Hermes** | Thread-based `delegate_task` | ✅ Synchronous (default) | `max_concurrent_children` config |
| **OpenCode** | Session-based subagent invocation | ⚠️ Asynchronous (session-based) | No explicit control |
| **OpenClaw** | Session-based `sessions_spawn` | ❌ Non-blocking (push-based) | No explicit control |

**Trade-offs**:
- **Hermes**: Simple mental model, but blocks parent until all subagents complete
- **OpenCode**: Flexible session navigation, but no explicit concurrency control
- **OpenClaw**: Most flexible (non-blocking), but complex completion delivery logic

### Monitoring & Reliability

| Framework | Heartbeat | Stale Detection | Timeout | Diagnostics |
|-----------|-----------|-----------------|---------|-------------|
| **Hermes** | ✅ Yes | ✅ Yes | ✅ Hard timeout | ✅ 0-API-call diagnostic |
| **OpenCode** | ❌ No | ❌ No | ❌ No | ❌ No |
| **OpenClaw** | ❌ No | ❌ No | ❌ No | ❌ No |

**Key Insight**: Hermes is the only framework with production-grade monitoring. OpenCode and OpenClaw rely on session-level timeouts and external monitoring.

### Context Isolation

| Framework | Isolation Model | Context Modes | Token Efficiency |
|-----------|----------------|---------------|------------------|
| **Hermes** | Fresh context per subagent | ✅ Isolated only | ✅ Low (no parent context) |
| **OpenCode** | Session-based isolation | ✅ Session-based | ⚠️ Medium (session overhead) |
| **OpenClaw** | Configurable isolation | ✅ Isolated + Fork | ✅ Low (isolated) / ⚠️ High (fork) |

**Trade-offs**:
- **Hermes**: Most token-efficient, but subagents lack parent context
- **OpenCode**: Session overhead, but persistent context across interactions
- **OpenClaw**: Flexible (isolated for efficiency, fork for context-sensitive work)

### Tool Isolation

| Framework | Isolation Model | Blocked Tools | Configurable? |
|-----------|----------------|---------------|---------------|
| **Hermes** | Explicit toolset selection | `delegate_task`, `clarify`, `memory`, `send_message` | ✅ Yes (per subagent) |
| **OpenCode** | Permission-based | Configurable per agent (allow/deny/ask) | ✅ Yes (per agent) |
| **OpenClaw** | Tool policy-based | `message` tool blocked by default | ⚠️ Limited (policy-based) |

**Key Insight**: Hermes has the most explicit tool isolation (toolset selection), OpenCode has the most flexible (permission-based), OpenClaw has the simplest (policy-based).

### Nesting Control

| Framework | Max Depth | Configurable? | Opt-In? |
|-----------|-----------|---------------|---------|
| **Hermes** | 5 (default) | ✅ Yes | ✅ Yes (orchestrator role) |
| **OpenCode** | No limit | ❌ No | ❌ No |
| **OpenClaw** | Configurable | ✅ Yes | ✅ Yes (per agent) |

**Trade-offs**:
- **Hermes**: Prevents unbounded nesting by default, opt-in for orchestrator patterns
- **OpenCode**: No nesting control, relies on LLM to avoid infinite recursion
- **OpenClaw**: Flexible nesting control, per-agent configuration

---

## TestAI Comparison

### Current Implementation

**Model**: Thread-based `delegate_task` (similar to Hermes)

**Strengths**:
- ✅ Parallel execution via `_run_batch`
- ✅ Background mode via `_run_batch_background`
- ✅ Session persistence in database
- ✅ Tool isolation via toolsets

**Weaknesses**:
- ❌ No heartbeat monitoring (gateway timeout risk)
- ❌ No stale detection (hung subagents not detected)
- ❌ No hard timeout per subagent (indefinite blocking)
- ❌ No 0-API-call diagnostics (stuck subagents are black boxes)
- ❌ No credential pooling (subagents don't share parent credentials)

### Recommendations

**Priority 1: Heartbeat Monitoring** (Hermes pattern)
- Implement heartbeat loop in `_run_single_enhanced`
- Propagate child activity to parent to prevent gateway timeouts
- Add stale detection with configurable thresholds

**Priority 2: Timeout Management** (Hermes pattern)
- Add hard timeout per subagent (configurable via `delegation.child_timeout`)
- Implement timeout executor with thread capture
- Add 0-API-call diagnostic for stuck subagents

**Priority 3: Stale Detection** (Hermes pattern)
- Monitor tool/iteration progress in heartbeat loop
- Count cycles without progress to detect hung subagents
- Use different thresholds for idle vs in-tool subagents

**Priority 4: Context Modes** (OpenClaw pattern)
- Add `isolated` mode (default, fresh context)
- Add `fork` mode (branched from parent, context-sensitive work)
- Allow per-spawn configuration

**Priority 5: Push-Based Completion** (OpenClaw pattern)
- Implement non-blocking spawn with run ID return
- Add completion delivery with retry logic
- Use idempotency keys for exactly-once delivery

---

## Conclusion

**Hermes** is the most production-ready framework with heartbeat monitoring, stale detection, and timeout management. Its thread-based model is simple and reliable.

**OpenCode** is the most flexible with session-based isolation and navigation, but lacks monitoring and timeout management.

**OpenClaw** is the most sophisticated with push-based completion, context modes, and ACP integration, but is also the most complex.

**TestAI** should adopt Hermes's monitoring patterns (heartbeat, stale detection, timeout) as the highest priority, then consider OpenClaw's push-based completion model for improved flexibility.

---

*Document created: 2026-06-18*  
*Author: TestAI E2E Test Suite*  
*Status: COMPLETE*

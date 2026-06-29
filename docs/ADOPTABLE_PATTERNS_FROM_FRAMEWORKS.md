# Adoptable Patterns from Open-Source Agent Frameworks

> **Date:** 2026-06-17
> **Source frameworks:** OpenHands, SWE-agent, Claude Code, Hermes, LangGraph, CrewAI
> **Goal:** Features and patterns we can directly adopt into TestAI

---

## 1. Sandbox Lifecycle (from OpenHands + Modal)

### What they do:
- **Snapshot/Restore:** Save Docker layer state, restore for future sessions
- **Timeout-based cleanup:** Auto-destroy after configurable lifetime
- **Detach pattern:** Run agent, snapshot, terminate — clean lifecycle

### What we can adopt:
```python
# Current: Manual sandbox management
# Adopt: Auto-snapshot at milestones + timeout-based cleanup

class SandboxLifecycle:
    def auto_snapshot(self, session_id, milestone="post_deps_install"):
        """Snapshot after dependency installation for future restores."""
        snapshot_id = self.snapshot(session_id)
        self.store_snapshot_mapping(session_id, snapshot_id, milestone)
    
    def cleanup_idle(self, max_idle_seconds=3600):
        """Destroy sandboxes idle超过1小时."""
        for sb in self.list_active():
            if sb.idle_seconds > max_idle_seconds:
                self.destroy(sb.session_id)
    
    def restore_from_snapshot(self, session_id, milestone="post_deps_install"):
        """Restore from nearest snapshot for faster bootstrap."""
        snapshot = self.get_nearest_snapshot(session_id, milestone)
        if snapshot:
            return self.restore(snapshot)
        return self.create_new(session_id)
```

### Priority: HIGH — Direct impact on agent bootstrap time

---

## 2. Tool Execution Patterns (from Hermes)

### What they do:
- **Concurrent execution:** Multiple tool calls executed via ThreadPoolExecutor
- **Interactive tool forcing:** Tools like `clarify` force sequential execution
- **Result reordering:** Results reinserted in original call order regardless of completion
- **Error wrapping:** Consistent error format across all tools
- **Async bridging:** Sync/async tool handlers unified

### What we can adopt:
```python
# Current: Sequential tool execution
# Adopt: Concurrent execution with ordering preserved

async def execute_tool_calls(self, tool_calls: list) -> list:
    """Execute tool calls concurrently, preserving order."""
    if len(tool_calls) == 1:
        return [await self.execute_single(tool_calls[0])]
    
    # Mark interactive tools for sequential execution
    interactive_tools = {"question", "clarify", "computer_use"}
    has_interactive = any(tc.name in interactive_tools for tc in tool_calls)
    
    if has_interactive:
        # Sequential for interactive tools
        return [await self.execute_single(tc) for tc in tool_calls]
    
    # Concurrent for non-interactive tools
    results = [None] * len(tool_calls)
    async def run_with_index(idx, tc):
        results[idx] = await self.execute_single(tc)
    
    await asyncio.gather(*[
        run_with_index(i, tc) for i, tc in enumerate(tool_calls)
    ])
    return results
```

### Priority: HIGH — 2-3x speedup for parallel tool calls

---

## 3. Permission Modes (from Claude Code)

### What they do:
- **Granular permissions:** allow/ask/deny per tool with glob patterns
- **Mode-based gating:** default, plan, auto, bypassPermissions modes
- **File-level restrictions:** `Read(./secrets/**)` to deny sensitive files

### What we can adopt:
```python
# Current: Simple allow/deny per tool
# Adopt: Glob-based permission rules

PERMISSION_RULES = {
    "allow": [
        "bash(git diff *)",
        "read_file(./src/**/*.py)",
        "codegraph_explore",
    ],
    "ask": [
        "bash(git push *)",
        "write_file(./.env*)",
    ],
    "deny": [
        "read_file(./secrets/**)",
        "bash(rm -rf *)",
    ]
}

def check_permission(tool_name: str, args: dict, rules: dict) -> str:
    """Check if tool call is allowed, needs ask, or denied."""
    for rule in rules.get("deny", []):
        if matches_pattern(tool_name, args, rule):
            return "deny"
    for rule in rules.get("ask", []):
        if matches_pattern(tool_name, args, rule):
            return "ask"
    return "allow"
```

### Priority: MEDIUM — Better security model

---

## 4. Background Agent Execution (from Claude Code)

### What they do:
- **Fire-and-forget:** Spawn agent, get ID, continue working
- **Status polling:** Check agent status via ID
- **Result collection:** Retrieve results when ready

### What we can adopt:
```python
# Current: Background mode exists but not well-integrated
# Adopt: Full lifecycle management

class BackgroundAgentManager:
    async def spawn_background(self, goal, model=None) -> str:
        """Spawn background agent, return subagent_id."""
        subagent_id = await self.delegate_task(
            goal=goal,
            run_in_background=True,
            model=model,
        )
        return subagent_id
    
    async def get_status(self, subagent_id: str) -> dict:
        """Get background agent status."""
        return await self.collect_results([subagent_id])
    
    async def wait_for_completion(self, subagent_id: str, timeout: int = 300):
        """Wait for background agent to complete."""
        result = await self.collect_results(
            [subagent_id], timeout=timeout
        )
        return result.get(subagent_id)
```

### Priority: MEDIUM — Better UX for long-running tasks

---

## 5. Checkpoint/Resume (from LangGraph)

### What they do:
- **Thread-based persistence:** Full graph state snapshots
- **Granular checkpoints:** Per-superstep persistence
- **Human-in-the-loop:** Pause, get approval, resume

### What we can adopt:
```python
# Current: Basic checkpoint exists
# Adopt: Granular checkpoints with approval gates

class CheckpointManager:
    async def checkpoint_before_action(self, action_type: str):
        """Checkpoint before destructive actions."""
        if action_type in ("write_file", "bash", "commit"):
            await self.save_checkpoint(
                type=action_type,
                messages_snapshot=self.messages,
                tool_state=self.tool_state,
            )
    
    async def resume_from_checkpoint(self, checkpoint_id: str):
        """Resume from specific checkpoint."""
        checkpoint = await self.load_checkpoint(checkpoint_id)
        self.messages = checkpoint.messages_snapshot
        self.tool_state = checkpoint.tool_state
```

### Priority: MEDIUM — Better fault tolerance

---

## 6. Self-Healing Patterns (from SWE-agent)

### What they do:
- **Retry tokens:** `RETRY_WITH_OUTPUT_TOKEN` for retry logic
- **Exit forfeit:** Give up after max retries
- **Output-based retry:** Retry with context from previous failure

### What we can adopt:
```python
# Current: Basic retry in attempt_heal
# Adopt: Structured retry with context

class SelfHealer:
    RETRY_MARKERS = {
        "retry_with_context": "###RETRY-WITH-CONTEXT###",
        "retry_without_context": "###RETRY-WITHOUT-CONTEXT###",
        "exit_forfeit": "###EXIT-FORFEIT###",
    }
    
    async def heal_with_context(self, error, previous_attempts):
        """Heal using context from previous failures."""
        context = self.build_context(error, previous_attempts)
        return await self.attempt_heal(
            error=error,
            context=context,
            max_retries=3,
        )
```

### Priority: MEDIUM — Better self-healing success rate

---

## 7. Heartbeat Pattern (from Hermes)

### What they do:
- **Periodic heartbeat:** Agent signals it's still alive
- **Stale detection:** Dispatcher reclaims stale claims
- **Long operation signal:** Prevents timeout during long tasks

### What we can adopt:
```python
# Current: kanban_heartbeat exists but not auto-triggered
# Adopt: Auto-heartbeat during long operations

class AutoHeartbeat:
    HEARTBEAT_INTERVAL = 3600  # 1 hour
    
    async def run_with_heartbeat(self, agent_func):
        """Run agent with automatic heartbeat."""
        last_heartbeat = time.time()
        
        async for event in agent_func():
            yield event
            
            # Auto-heartbeat every hour
            if time.time() - last_heartbeat > self.HEARTBEAT_INTERVAL:
                await self.kanban_heartbeat(
                    note="Still working on task..."
                )
                last_heartbeat = time.time()
```

### Priority: LOW — Nice to have for long tasks

---

## 8. Event-Sourced State (from OpenHands)

### What they do:
- **Immutable events:** All state changes as events
- **Replay capability:** Rebuild state from event log
- **Audit trail:** Complete history of all actions

### What we can adopt:
```python
# Current: Events emitted but not used for state
# Adopt: Event-sourced state management

class EventSourcedAgent:
    def __init__(self):
        self.events = []
        self.state = {}
    
    async def emit_event(self, event_type, data):
        """Emit event and update state."""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }
        self.events.append(event)
        self.apply_event(event)
    
    def apply_event(self, event):
        """Apply event to state."""
        if event["type"] == "tool_executed":
            self.state["tool_calls"] = self.state.get("tool_calls", 0) + 1
        elif event["type"] == "tokens_generated":
            self.state["tokens"] = self.state.get("tokens", 0) + event["data"]["count"]
    
    def get_state_snapshot(self):
        """Get current state snapshot."""
        return {
            "state": self.state,
            "event_count": len(self.events),
            "last_event": self.events[-1] if self.events else None,
        }
```

### Priority: LOW — Nice for debugging/auditing

---

## 9. MCP Interceptor Pattern (from LangChain)

### What they do:
- **Request interception:** Modify tool calls before execution
- **Dynamic headers:** Add auth headers based on context
- **Logging:** Automatic tool call logging

### What we can adopt:
```python
# Current: Direct tool execution
# Adopt: Interceptor pattern for cross-cutting concerns

class ToolInterceptor:
    async def before_execute(self, tool_name, args):
        """Intercept before tool execution."""
        # Log tool call
        logger.info(f"Tool call: {tool_name}({args})")
        
        # Add auth headers for external tools
        if tool_name.startswith("github_"):
            args["token"] = self.get_github_token()
        
        return args
    
    async def after_execute(self, tool_name, args, result):
        """Intercept after tool execution."""
        # Record metrics
        self.metrics.record(tool_name, duration=time.time() - start)
        
        # Sanitize sensitive data from logs
        if tool_name in ("bash", "write_file"):
            result = self.sanitize(result)
        
        return result
```

### Priority: MEDIUM — Better observability

---

## 10. Subagent Type System (from Claude Code)

### What they do:
- **Named subagent types:** code-reviewer, test-writer, etc.
- **Inherited model:** Subagents inherit model from parent
- **Tool restrictions:** Each type has specific allowed tools

### What we can adopt:
```python
# Current: Role-based but not type-safe
# Adopt: Typed subagent system

class SubagentType:
    CODE_REVIEWER = "code-reviewer"
    TEST_WRITER = "test-writer"
    BUG_FIXER = "bug-fixer"
    SECURITY_AUDITOR = "security-auditor"
    DOCS_WRITER = "docs-writer"

SUBAGENT_CONFIGS = {
    SubagentType.CODE_REVIEWER: {
        "tools": ["read_file", "glob", "grep", "codegraph_explore"],
        "model": "inherit",  # Inherit from parent
        "description": "Read-only code review",
    },
    SubagentType.TEST_WRITER: {
        "tools": ["bash", "read_file", "write_file", "glob", "grep"],
        "model": "inherit",
        "description": "Write and run tests",
    },
}
```

### Priority: LOW — Already have role system

---

## Summary: Priority Matrix

| Priority | Pattern | Source | Effort | Impact |
|----------|---------|--------|--------|--------|
| HIGH | Concurrent tool execution | Hermes | Low | 2-3x speedup |
| HIGH | Sandbox auto-snapshot | OpenHands/Modal | Medium | Faster bootstrap |
| HIGH | Sandbox idle cleanup | Modal | Low | Resource savings |
| MEDIUM | Permission modes | Claude Code | Medium | Better security |
| MEDIUM | Background agent lifecycle | Claude Code | Medium | Better UX |
| MEDIUM | Granular checkpoints | LangGraph | Medium | Fault tolerance |
| MEDIUM | Self-healing with context | SWE-agent | Medium | Better success rate |
| MEDIUM | Tool interceptors | LangChain | Low | Better observability |
| LOW | Auto-heartbeat | Hermes | Low | Long task support |
| LOW | Event-sourced state | OpenHands | High | Debugging/audit |
| LOW | Typed subagent system | Claude Code | Low | Already have roles |

---

*Document created: 2026-06-17*

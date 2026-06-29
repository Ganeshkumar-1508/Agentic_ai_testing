# Reference Implementations — Adoptable Patterns

> **Date:** 2026-06-17
> **Sources:** hermes-agent, openclaude, OpenHands, OpenHarness
> **Goal:** Specific code patterns we can adopt into TestAI

---

## 1. Hermes Agent — File State Coordination

### What it does:
**File:** `reference/hermes-agent/tools/file_state.py`

Prevents mangled edits when concurrent subagents touch the same file. Tracks:
- Per-agent read stamps: `{task_id: {path: (mtime, read_ts, partial)}}`
- Last writer globally: `{path: (task_id, write_ts)}`
- Per-path locks for read→modify→write critical sections

### What we should adopt:
```python
# Current: No file state tracking between subagents
# Adopt: FileStateRegistry for cross-agent coordination

class FileStateRegistry:
    def __init__(self):
        self._reads = defaultdict(dict)  # {task_id: {path: stamp}}
        self._last_writer = {}           # {path: (task_id, write_ts)}
        self._path_locks = {}            # {path: Lock}
    
    def record_read(self, task_id, path, partial=False):
        """Record that an agent read a file."""
        mtime = os.path.getmtime(path)
        self._reads[task_id][path] = (mtime, time.time(), partial)
    
    def check_stale(self, task_id, path):
        """Check if file was modified since last read."""
        if task_id not in self._reads:
            return False
        if path not in self._reads[task_id]:
            return False
        last_mtime, _, _ = self._reads[task_id][path]
        current_mtime = os.path.getmtime(path)
        return current_mtime > last_mtime
    
    def note_write(self, task_id, path):
        """Record that an agent wrote a file."""
        self._last_writer[path] = (task_id, time.time())
    
    @contextmanager
    def lock_path(self, path):
        """Acquire per-path lock for read→modify→write."""
        lock = self._get_lock(path)
        with lock:
            yield
```

### Priority: HIGH — Prevents concurrent subagent file corruption

---

## 2. Hermes Agent — Process Registry

### What it does:
**File:** `reference/hermes-agent/tools/process_registry.py`

In-memory registry for managed background processes with:
- Output buffering (rolling 200KB window)
- Status polling and log retrieval
- Blocking wait with interrupt support
- Process killing
- Crash recovery via JSON checkpoint file

### What we should adopt:
```python
# Current: Basic background task tracking
# Adopt: Full process registry with checkpoint recovery

class ProcessRegistry:
    def __init__(self, checkpoint_path):
        self._processes = {}
        self._checkpoint_path = checkpoint_path
    
    def spawn(self, env, command, task_id=None):
        """Spawn background process with tracking."""
        session = ProcessSession(
            id=str(uuid.uuid4()),
            command=command,
            task_id=task_id,
        )
        self._processes[session.id] = session
        self._save_checkpoint()
        return session
    
    def poll(self, session_id):
        """Get process status."""
        session = self._processes.get(session_id)
        if not session:
            return None
        return {
            "status": session.status,
            "output": session.get_output(),
            "exit_code": session.exit_code,
        }
    
    def wait(self, session_id, timeout=300):
        """Block until process completes."""
        # ... implementation
    
    def _save_checkpoint(self):
        """Save state to JSON for crash recovery."""
        state = {sid: s.to_dict() for sid, s in self._processes.items()}
        with open(self._checkpoint_path, 'w') as f:
            json.dump(state, f)
```

### Priority: MEDIUM — Better background process management

---

## 3. Hermes Agent — OSV Malware Check

### What it does:
**File:** `reference/hermes-agent/tools/osv_check.py`

Before launching MCP servers via npx/uvx, queries OSV API to check for malware advisories. Fail-open on network errors.

### What we should adopt:
```python
# Current: No package security scanning
# Adopt: OSV check for MCP packages

def check_package_for_malware(command, args):
    """Check if MCP package has known malware."""
    ecosystem = _infer_ecosystem(command)  # npx → npm, uvx → PyPI
    if not ecosystem:
        return None
    
    package, version = _parse_package_from_args(args, ecosystem)
    if not package:
        return None
    
    try:
        malware = _query_osv(package, ecosystem, version)
    except Exception:
        return None  # Fail-open
    
    if malware:
        return f"BLOCKED: Package '{package}' has malware: {malware[0]['id']}"
    return None
```

### Priority: MEDIUM — Security for MCP packages

---

## 4. Hermes Agent — Delegate Tool (Subagent Architecture)

### What it does:
**File:** `reference/hermes-agent/tools/delegate_tool.py`

Spawns child agents with:
- Fresh conversation (no parent history)
- Restricted toolset (blocked tools always stripped)
- Focused system prompt
- Parent only sees delegation call + summary result

### Key patterns:
```python
# Blocked tools for subagents
DELEGATE_BLOCKED_TOOLS = frozenset([
    "delegate_task",  # No recursive delegation
    "clarify",        # No user interaction
    "memory",         # No writes to shared memory
    "send_message",   # No cross-platform side effects
    "execute_code",   # Children should reason step-by-step
])

# Subagent approval callbacks
def _subagent_auto_deny(command, description, **kwargs):
    """Auto-deny dangerous commands in subagent threads."""
    logger.warning("Subagent auto-denied: %s", command)
    return "deny"

def _subagent_auto_approve(command, description, **kwargs):
    """Auto-approve in subagent threads (opt-in YOLO)."""
    logger.warning("Subagent auto-approved: %s", command)
    return "once"
```

### Priority: HIGH — We already have this, but can improve

---

## 5. Hermes Agent — Checkpoint Manager (Git-based)

### What it does:
**File:** `reference/hermes-agent/tools/checkpoint_manager.py`

Creates automatic snapshots of working directories before file-mutating operations using a single shared shadow git store. Provides rollback to any previous checkpoint.

### Key patterns:
```python
# Single shared store (deduplicates across projects)
CHECKPOINT_BASE = get_hermes_home() / "checkpoints"
_STORE_DIRNAME = "store"

# Auto-maintenance
def prune_checkpoints(retention_days=30, max_total_size_mb=500):
    """Delete orphaned/stale checkpoints, run git gc."""
    # ...

# Storage layout:
# ~/.hermes/checkpoints/
#     store/                          — single bare-ish git repo
#         HEAD, config, objects/      — standard git internals
#         refs/hermes/<hash16>        — per-project branch tip
#         indexes/<hash16>            — per-project git index
#         projects/<hash16>.json      — {workdir, created_at, last_touch}
```

### Priority: HIGH — Better checkpoint system than our DB-only approach

---

## 6. Hermes Agent — Approval System

### What it does:
**File:** `reference/hermes-agent/tools/approval.py`

Dangerous command approval with:
- Pattern detection (DANGEROUS_PATTERNS)
- Per-session approval state (thread-safe)
- Smart approval via auxiliary LLM
- Permanent allowlist persistence

### Key patterns:
```python
# Per-session approval state
_approval_session_key = contextvars.ContextVar("approval_session_key", default="")

# Approval flow
def prompt_dangerous_approval(command, description, **kwargs):
    """Check if command needs approval."""
    session_key = get_current_session_key()
    
    # Check permanent allowlist
    if is_permanently_allowed(command, session_key):
        return "allow"
    
    # Check YOLO mode
    if _YOLO_MODE_FROZEN:
        return "allow"
    
    # Ask user or smart-approve via LLM
    return ask_user_approval(command, description)
```

### Priority: MEDIUM — Better approval UX

---

## 7. OpenHands — Event Store

### What it does:
**File:** `reference/OpenHands/openhands/app_server/event/`

Event-sourced architecture with:
- Event store (filesystem, S3, Google Cloud)
- Event callbacks (webhooks)
- Event routing

### Key patterns:
```python
# Event store interface
class EventStore:
    async def append(self, event: Event) -> None:
        """Append event to store."""
        pass
    
    async def get_events(self, session_id: str, limit: int = 100) -> list[Event]:
        """Get events for session."""
        pass

# Event types
class EventType(str, Enum):
    AGENT_THOUGHT = "agent_thought"
    ACTION = "action"
    OBSERVATION = "observation"
    MESSAGE = "message"
```

### Priority: LOW — We already have event emission

---

## 8. OpenHarness — Swarm Architecture

### What it does:
**File:** `reference/OpenHarness/src/openharness/swarm/`

Multi-agent coordination with:
- In-process spawning
- Subprocess backend
- Mailbox for inter-agent communication
- Worktree for parallel file access
- Team lifecycle management

### Key patterns:
```python
# Swarm types
class SwarmMode(Enum):
    IN_PROCESS = "in_process"  # Same process, thread-based
    SUBPROCESS = "subprocess"  # Separate process

# Mailbox for inter-agent communication
class Mailbox:
    def send(self, agent_id: str, message: dict) -> None:
        """Send message to agent."""
        pass
    
    def receive(self, agent_id: str) -> list[dict]:
        """Receive messages for agent."""
        pass

# Worktree for parallel file access
class Worktree:
    def create(self, branch: str) -> str:
        """Create git worktree for parallel work."""
        pass
    
    def destroy(self, branch: str) -> None:
        """Destroy worktree."""
        pass
```

### Priority: MEDIUM — Better multi-agent coordination

---

## 9. OpenHarness — Memory System

### What it does:
**File:** `reference/OpenHarness/src/openharness/memory/`

Memory management with:
- Agent-specific memory
- Team memory (shared across agents)
- Memory relevance scoring
- Memory migration

### Key patterns:
```python
# Memory types
class MemoryType(Enum):
    AGENT = "agent"      # Per-agent memory
    TEAM = "team"        # Shared team memory
    SESSION = "session"  # Per-session memory

# Memory manager
class MemoryManager:
    def __init__(self, base_path):
        self.base_path = base_path
    
    def store(self, key, value, memory_type=MemoryType.AGENT):
        """Store memory entry."""
        pass
    
    def retrieve(self, key, memory_type=MemoryType.AGENT):
        """Retrieve memory entry."""
        pass
    
    def search(self, query, limit=10):
        """Search memory by relevance."""
        pass
```

### Priority: MEDIUM — Better memory system

---

## 10. OpenHarness — Task Manager

### What it does:
**File:** `reference/OpenHarness/src/openharness/tasks/`

Task management with:
- Local agent tasks
- Local shell tasks
- Task lifecycle (create, run, stop)
- Task output capture

### Key patterns:
```python
# Task types
class TaskType(Enum):
    LOCAL_AGENT = "local_agent"  # Run agent locally
    LOCAL_SHELL = "local_shell"  # Run shell command locally

# Task manager
class TaskManager:
    def __init__(self):
        self._tasks = {}
    
    def create_task(self, task_type, config) -> Task:
        """Create a new task."""
        pass
    
    def run_task(self, task_id) -> TaskResult:
        """Run task and return result."""
        pass
    
    def stop_task(self, task_id) -> None:
        """Stop running task."""
        pass
```

### Priority: LOW — We have todo system

---

## Summary: Priority Matrix from Reference Implementations

| Priority | Pattern | Source | Effort | Impact |
|----------|---------|--------|--------|--------|
| HIGH | File state coordination | Hermes | Medium | Prevents concurrent edits |
| HIGH | Git-based checkpoint system | Hermes | High | Better rollback/recovery |
| HIGH | Delegate tool improvements | Hermes | Low | Better subagent isolation |
| MEDIUM | OSV malware check | Hermes | Low | Security for MCP packages |
| MEDIUM | Process registry | Hermes | Medium | Better background tasks |
| MEDIUM | Approval system | Hermes | Medium | Better UX |
| MEDIUM | Swarm architecture | OpenHarness | High | Better multi-agent |
| MEDIUM | Memory system | OpenHarness | Medium | Better memory |
| LOW | Event store | OpenHands | Low | We have events |
| LOW | Task manager | OpenHarness | Low | We have todo |

---

## Top 3 Quick Wins

1. **File State Coordination (Hermes)** — Prevents concurrent subagent file corruption
2. **OSV Malware Check (Hermes)** — Security for MCP packages
3. **Git-based Checkpoints (Hermes)** — Better rollback than DB-only

---

*Document created: 2026-06-17*

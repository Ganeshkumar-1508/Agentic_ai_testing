# TestAI — Gaps, Missing Features & Architecture Issues

**Date:** 2026-06-25  
**Scope:** Detailed breakdown of every gap, missing feature, and architectural issue discovered during the comprehensive audit  
**Based on:** Codebase audit + F1-F35 findings from 2026-06-24 e2e run + competitive research (Greptile TREX, Tembo AI, TestSprite, Testim, Mabl, Bug0, E2B, Modal, Daytona, Claude Code, GitHub Copilot, Devin, Hermes, OpenCode, OpenClaw)

---

## PRIORITY MATRIX

| # | Gap | Section | Priority | Effort | Phase |
|---|-----|---------|----------|--------|-------|
| G2 | ~~No stuck detector (5 patterns, only 1 detected)~~ ✅ FIXED | 2.1 | FIXED | 0 | — |
| G3 | ~~No semantic triple extraction (KG)~~ ✅ RESOLVED | 3.1 | RESOLVED | 0 | — |
| G4 | Goal decomposition hallucination (F6) | 7.2 | HIGH | 1d | Phase 1 |
| G5 | No per-subagent sandbox | 1.3 | HIGH | 5-7d | Phase 2 |
| G7 | No OpenTelemetry export | 4.1 | HIGH | 3-5d | Phase 3 |
| G8 | ~~No GitHub Issues/PRs integration~~ ✅ FIXED | 5.2 | FIXED | 0 | — |
| G9 | No session-aware chat agent | 5.3 | HIGH | 3-5d | Phase 5 |
| G10 | No hard timeout per subagent | 2.3 | HIGH | 2-3d | Phase 1 |
| G11 | Container name truncation (F7) | 1.2 | MEDIUM | <1d | Phase 1 |
| G12 | Kanban column default mismatch (F10) | 7.1 | MEDIUM | <1d | Phase 1 |
| G13 | System prompt leaks into task titles (F19) | 7.3 | MEDIUM | <1d | Phase 1 |
| G14 | 3 entry points, no clear default | 5.1 | MEDIUM | 2-3d | Phase 4 |
| G15 | No OTel cancel/interrupt event type | 4.3 | MEDIUM | 2-3d | Phase 3 |
| G16 | No per-tool latency metrics p50/p95 | 4.2 | MEDIUM | 1-2d | Phase 3 |
| G18 | Circuit breaker per-role config | 8.1 | MEDIUM | 2-3d | Phase 2 |
| G19 | ~~Zombie subagent sessions (F5)~~ ✅ FIXED | 2.9 | FIXED | 0 | — |
| G20 | ErrorEvent missing structured diagnostics (F24) | 6.5 | MEDIUM | 1-2d | Phase 3 |
| G21 | No network isolation modes | 1.4 | MEDIUM | 2-3d | Phase 2 |
| G22 | No cross-repo volume sharing | 9.1 | MEDIUM | 2-3d | Phase 4 |
| G23 | No sandbox idle reaper | 9.2 | MEDIUM | 2-3d | Phase 2 |
| G24 | No orchestrator integration tests | 10.1 | MEDIUM | 3-5d | Phase 3 |
| G25 | No subagent-level resume | 2.7 | MEDIUM | 3-5d | Phase 2 |
| G26 | No context modes (isolated/fork) | 2.5 | LOW | 2-3d | Phase 4 |
| G27 | No push-based completion | 2.6 | LOW | 3-5d | Phase 4 |
| G28 | ~~No compaction agent~~ ✅ RESOLVED | 3.4 | RESOLVED | 0 | — |
| G29 | ~~No cross-run memory curation (L2)~~ ✅ RESOLVED | 3.3 | RESOLVED | 0 | — |
| G30 | No per-subagent memory isolation | 3.5 | LOW | 2-3d | Phase 4 |
| G31 | Memory tool text-only entries | 3.6 | LOW | 3-5d | Phase 4 |
| G32 | No per-tool cost tracking | 8.2 | LOW | 2-3d | Phase 3 |
| G33 | No per-role spawn rate limits | 8.3 | LOW | 1-2d | Phase 2 |
| G34 | No per-subagent budget cap | 8.4 | LOW | 2-3d | Phase 2 |
| G35 | ~~No skill versioning or testing~~ ✅ FIXED | 6.4 | FIXED | 0 | — |
| G36 | No codegraph tool tests | 6.1 | LOW | 2-3d | Phase 3 |
| G37 | No persistent tool health tracking | 6.2 | LOW | 3-5d | Phase 3 |
| G38 | ~~No live sandbox terminal streaming~~ ✅ FIXED | 4.4 | FIXED | 0 | — |
| G39 | ~~Pipeline-store dead component cleanup~~ ✅ RESOLVED | 4.5 | RESOLVED | 0 | — |
| G40 | No kanban task dependency tracking | 7.4 | LOW | 2-3d | Phase 4 |
| G41 | No kanban task time estimation | 7.5 | LOW | 1-2d | Phase 4 |
| G42 | Cross-session chat context | 5.5 | LOW | 2-3d | Phase 5 |
| G43 | ~~No user-configurable sandbox~~ ✅ FIXED | 5.4 | FIXED | 0 | — |
| G44 | No user-configurable artifact lifecycle | 9.4 | LOW | 2-3d | Phase 5 |
| G45 | No flaky test detection | 10.3 | LOW | 3-5d | Phase 4 |
| G46 | No test result → artifact linking | 10.4 | LOW | 1-2d | Phase 3 |
| G47 | No multi-repo coordination | 9.3 | LOW | 5-7d | Phase 5 |
| G48 | No CI/CD e2e pipeline test | 10.2 | LOW | 3-5d | Phase 3 |
| G49 | No GPU support | 1.5 | LOW | 3-5d | Future |
| G50 | No gVisor/Firecracker isolation | 1.6 | LOW | 2-4w | Future |

### Phase Plan

| Phase | Timeline | Gaps | Focus |
|-------|----------|------|-------|
| **Phase 1: Reliability** | Week 1-2 | G4, G10, G11, G12, G13, G19 | Fix immediate bugs, add stuck detection, timeouts |
| **Phase 2: Isolation** | Week 2-3 | G5, G18, G21, G23, G25, G33, G34 | Per-subagent sandbox, circuit breaker config, network isolation |
| **Phase 3: Observability** | Week 3-4 | G7, G15, G16, G20, G24, G32, G36, G37, G38, G39, G46, G48 | OTel export, latency metrics, tool health, dead component cleanup |
| **Phase 4: Intelligence** | Week 4-6 | G14, G22, G26, G27, G29, G30, G31, G35, G40, G41, G45 | Compaction, context modes, skill versioning, flaky detection (G3, G28 resolved — see 3.1, 3.4) |
| **Phase 5: User Facing** | Week 6-8 | G8, G9, G42, G43, G44, G47 | GitHub integration, chat agent, sandbox config, artifact lifecycle, multi-repo |

---

## SECTION CONTENTS

### 1.1 ~~No Worktree Isolation~~ ✅ IMPLEMENTED

**Status:** `WorktreeManager` is fully implemented at `backend/harness/services/worktree_manager.py` (707 lines), wired into `orchestrator.py:731` and `delegate_task.py:661/1044/1098`, and covered by 3 test files (~60 test cases). Uses git-worktree isolation per subagent with per-session and per-subagent worktrees, contextvar-based git runner propagation, and auto-cleanup on failure.

---

### 1.2 Container Name Truncation (F7)

**Files involved:** `backend/harness/sandbox_manager.py:_create_env()`, `backend/harness/sandbox/registry.py`

**What:** Docker container names are constructed as `testai-sandbox-{session_id[:12]}`. The prefix `testai-sandbox-` is 16 characters. Docker's container name limit is 64 characters. This leaves only 48 characters for the session ID segment. In the F1 finding from the June 24 e2e run, the actual container name observed was literally `testai-sandbox-` with zero session ID characters.

**Root cause analysis** (`backend/harness/sandbox_manager.py`):

The `_safe_session_segment()` function truncates the session ID to fit within the 50-character volume name limit:
```python
def _safe_session_segment(session_id: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9_.-]', '', session_id)
    max_vol = 50 - len(VOLUME_NAME_PREFIX)  # VOLUME_NAME_PREFIX = "testai-ws-"
    return safe[:max_vol]
```

But the container name uses `session_id[:12]` directly after the `testai-sandbox-` prefix — and there's no equivalent safety check. If `session_id` is empty, short, or URL-encoded, the container name becomes truncated or meaningless.

**Observed failure:**
```
$ docker ps --filter name=testai-sandbox-
testai-sandbox-        # No session id! 16 chars used, 0 for id
```

**Impact:**
- Operations teams cannot identify which container belongs to which job
- `docker logs testai-sandbox-` is ambiguous
- The `_recover_containers()` method parses container names to rebuild state — with truncated names, recovery produces wrong mappings
- Monitoring dashboards can't link container metrics to job metrics
- When multiple jobs run simultaneously, their containers are indistinguishable

**Fix options:**

**Option A — Shorten prefix** (recommended, <1 day):
```python
CONTAINER_NAME_PREFIX = "tsb-"  # Was "testai-sandbox-"
# This gives 61 chars for session segment instead of 48
```

**Option B — Use Docker labels** (recommended as additional fix, 1 day):
```python
# Add labels to ALL containers
labels = [
    ("testai-managed", "1"),
    ("testai-session-id", session_id),
    ("testai-run-id", run_id),
    ("testai-job-id", spec_id or ""),
]
# Query by label instead of name pattern
docker ps --filter label=testai-managed=1
```

**Option C — Validate session_id length** (defensive, <1 day):
```python
def _safe_container_name(session_id: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9_.-]', '', session_id)
    max_name = 64 - len(CONTAINER_NAME_PREFIX)
    if not safe:
        raise ValueError(f"Empty session_id after sanitization")
    return f"{CONTAINER_NAME_PREFIX}{safe[:max_name]}"
```

**Effort:** <1 day (all three options combined)

---

### 1.3 No Per-Subagent Sandbox

**Files involved:** `backend/harness/sandbox_manager.py:311-316` (get_or_create), `backend/harness/tools/subagent.py:994-1236` (spawn)

**What:** A single Docker container (`testai-sandbox-{session_id[:12]}`) serves every subagent in a session. The `SandboxManager.get_or_create()` method returns the same `SandboxEnvironment` for any caller with the same `session_id`. There is no subagent-level isolation — no per-subagent container, no per-subagent volume mount, no per-subagent resource limits.

**How the sharing happens (code trace):**

```
OrchestratorEngine.run_job_spec(spec)
  → SandboxManager.get_or_create(session_id="abc123")  # Creates container
  → Coordinator.spawn_many(goals=[...])                  # 5 subagents
    → Subagent.spawn(goal="explore auth")
      → SandboxManager.get_or_create("abc123")           # Returns SAME container
    → Subagent.spawn(goal="explore routes")
      → SandboxManager.get_or_create("abc123")           # Returns SAME container
    → Subagent.spawn(goal="explore tests")
      → SandboxManager.get_or_create("abc123")           # Returns SAME container
```

**Impact — detailed scenarios:**

*Scenario 1 — Conflicting dependency versions:*
```
Subagent A: pip install tensorflow==2.15  # Installs 800MB of deps
Subagent B: pip install tensorflow==2.16  # Overwrites A's install
Subagent C: Runs tests expecting 2.15 → FAILS
```

*Scenario 2 — Resource starvation:*
```
Subagent A: Starts a build that uses 8GB RAM (sandbox has 8GB total)
Subagent B: Tries to compile TypeScript → OOM killed
Subagent C: Tries to run tests → OOM killed
Result: All subagents fail except A
```

*Scenario 3 — Port conflicts:*
```
Subagent A: Starts dev server on port 3000
Subagent B: Starts dev server on port 3000 → EADDRINUSE
Subagent C: Tries to test on port 3000 → sees A's server, not B's
```

*Scenario 4 — State corruption:*
```
Subagent A: Writes to SQLite database at /workspace/data/dev.db
Subagent B: Reads /workspace/data/dev.db for its own tests
Subagent B: Gets wrong data because A's migration is half-done
```

**Competitor reference — E2B (Firecracker microVMs):**
```python
# E2B creates a dedicated microVM per execution
sandbox = Sandbox()
sandbox.run_code("pip install tensorflow==2.15")  # Isolated
sandbox2 = Sandbox()
sandbox2.run_code("pip install tensorflow==2.16")  # Separate VM, no conflict
```
- Boot time: ~150ms
- Isolation: Hardware-level (dedicated kernel per microVM)
- Pricing: $150/month + usage
- Max session: 24 hours

**Competitor reference — Modal (gVisor):**
```python
# Modal creates a gVisor sandbox per function call
@app.function(sandbox=True)
def train_model():
    # Runs in isolated gVisor sandbox
    pass
```
- Boot time: Sub-second
- Isolation: Syscall interception (user-space kernel)
- GPU: A100/H100 support
- Pricing: $250/month + usage

**Competitor reference — Daytona (OCI containers):**
- Boot time: 27-90ms (fastest in class)
- Isolation: Docker containers (same as TestAI)
- Key differentiator: Computer Use support (Windows/Linux/macOS GUI automation)
- Unlimited session length
- Open source, self-hostable

**Competitor reference — Tembo (Linux VMs):**
- 5 VM sizes: Micro (2 vCPU/4GB) → Ultra (32 vCPU/128GB)
- Full nested virtualization (Docker-in-Docker)
- VM boundary prevents all container-escape attacks
- Ephemeral — destroyed when session ends

**Fix options (recommended):**

**Option A — Per-subagent containers from shared base** (recommended, 5-7 days):
```python
# In subagent.py spawn(), create a new container per subagent
async def _create_subagent_sandbox(subagent_id, session_id):
    base_container = await sandbox_manager.get_or_create(session_id)
    # docker commit the base container's state
    snapshot_id = sandbox_manager.snapshot(session_id, label=f"sa-{subagent_id}")
    # Spawn a new container from the snapshot
    sa_env = await sandbox_manager.create_from_snapshot(
        snapshot_id=snapshot_id,
        subagent_id=subagent_id,
        resource_limits={"cpu": "1.0", "memory": "2g"}
    )
    return sa_env
```

**Option B — Subagent-scoped workspaces within shared container** (2-3 days, simpler):
```python
# Each subagent gets a chroot-like workspace directory
SUBAGENT_WORKSPACE = f"/workspace/.subagents/{subagent_id}"

async def _setup_subagent_workspace(subagent_id):
    ws = SUBAGENT_WORKSPACE
    os.makedirs(ws, exist_ok=True)
    # Symlink shared resources (node_modules, venv, etc.)
    for shared_dir in ["node_modules", ".venv", ".git"]:
        src = f"/workspace/{shared_dir}"
        dst = f"{ws}/{shared_dir}"
        if os.path.exists(src) and not os.path.exists(dst):
            os.symlink(src, dst)
    return ws
```

**Option C — Docker Compose per-subagent** (experimental, 7-10 days):
```yaml
# docker-compose.subagent.yml
services:
  subagent-{sa_id}:
    image: testai-sandbox:latest
    volumes:
      - shared-volume:/workspace:ro  # Read-only shared code
      - sa-{sa_id}-volume:/workspace/.sa  # Writable scratch
    networks:
      - subagent-{sa_id}-net  # Isolated network
    mem_limit: 2g
    cpus: 1.0
```

**Effort:** 2-3 days for Option B (quickest win), 5-7 days for Option A (production-grade)

---

### 1.4 No Network Isolation Modes

**Files involved:** `backend/harness/sandbox_manager.py:_effective_scope()`, `backend/harness/sandbox/sandbox_scope.py`

**What:** Sandbox containers use Docker's default bridge network, which allows unrestricted outbound access. The `SandboxScope` class has no network isolation configuration — no `egress_rules`, no `deny_all_dns`, no `allow_list`. Every sandbox container can reach any external service (GitHub, PyPI, npm, arbitrary IPs) by default.

**Current implementation** (`backend/harness/sandbox/sandbox_scope.py`, inferred):
```
SandboxScope:
  image: str | None
  network: str | None          # Only network name, not rules
  mounts: tuple[MountSpec, ...]
  labels: tuple[tuple[str, str], ...]
  # No network isolation attributes!
```

The actual Docker run command has no `--network` restriction:
```python
# sandbox_manager.py:_create_env() (approximate)
subprocess.run([
    "docker", "run", "-d",
    "--name", container_name,
    "--network", network or "testai-network",
    # No --cap-drop, no --security-opt, no iptables rules
    ...
])
```

**Impact:**

1. **Data exfiltration risk:** A compromised subagent (via prompt injection) can:
   - POST source code to an attacker's server
   - Download malicious packages from arbitrary registries
   - Exfiltrate environment variables (API keys, secrets)
   - Establish C2 (command & control) connections

2. **No audit trail:** Currently, there's no network egress logging. If something is exfiltrated, you have zero forensic visibility.

3. **Can't run sensitive workloads:** Organizations with compliance requirements (SOC 2, HIPAA, PCI) cannot allow unrestricted egress from agent sandboxes. This blocks enterprise adoption.

4. **No rate limiting:** A subagent can hammer external APIs without restriction, potentially:
   - Triggering rate limits on the host's external IP
   - Incurring unexpected cloud egress costs
   - Being flagged as a bot/DDoS source

**Competitor reference — E2B network modes:**

E2B offers three explicit network modes:
```python
# Mode 1: Allow-all (default for prototyping)
sandbox = Sandbox()  # Full network access

# Mode 2: Deny-all (for sensitive data processing)
sandbox = Sandbox(network=NetworkConfig(
    deny_all=True,  # Blocks ALL traffic including DNS
))

# Mode 3: User-defined rules (production)
sandbox = Sandbox(network=NetworkConfig(
    allow_list=[
        "github.com",           # Domain matching
        "pypi.org",
        "192.168.0.0/16",       # IP range matching
    ],
    deny_list=["*.internal.corp"],
))
```

**Competitor reference — Northflank zero-trust:**
> "AI agents should operate on a zero-trust network model where all connections are explicitly allowed rather than implicitly permitted."

Northflank's approach:
- **Egress filtering:** All outbound blocked by default
- **DNS restrictions:** Limit DNS resolution to prevent discovery attacks
- **Network segmentation:** Isolate agent networks from production systems

**Fix options:**

**Option A — Add SandboxNetworkConfig** (recommended, 2-3 days):
```python
# New class in sandbox/sandbox_scope.py
@dataclass
class SandboxNetworkConfig:
    mode: Literal["allow_all", "deny_all", "allow_list"] = "allow_all"
    allow_list: list[str] = field(default_factory=list)  # Domains/IPs
    deny_list: list[str] = field(default_factory=list)
    block_dns: bool = False
    log_egress: bool = False  # Audit logging

# Usage in SandboxManager:
scope = self._scope.with_overrides(
    network=SandboxNetworkConfig(
        mode="allow_list",
        allow_list=["github.com", "pypi.org", "api.openai.com"],
        log_egress=True,
    )
)
```

**Implementation approach for deny-all:**
```python
# Use Docker's --cap-drop and iptables within the container
docker run \
  --cap-drop=ALL \
  --cap-add=NET_RAW \
  --sysctl net.ipv4.ip_forward=0 \
  --dns 0.0.0.0  # Block DNS resolution
  # ... or use Docker network --internal flag:
  --network testai-internal  # No external access
```

**Option B — Docker network policies** (1-2 days, simpler):
```python
# Create named Docker networks with different isolation levels
docker network create testai-allow-all   # Default, unrestricted
docker network create testai-deny-all    # No external access (--internal flag)
docker network create testai-allow-list  # For future iptables rules

# SandboxManager picks the right network per scope
network_map = {
    "allow_all": "testai-allow-all",
    "deny_all": "testai-deny-all",
}
```

**Effort:** 2-3 days

---

### 1.5 No GPU Support

**Files involved:** `backend/harness/sandbox_manager.py:_create_env()`, Docker setup

**What:** Sandbox containers are launched without `--gpus all` or any GPU runtime configuration. There is no mechanism to request GPU resources per-sandbox or per-role.

**Current behavior:**
```python
# sandbox_manager.py:_create_env()  (approximate)
subprocess.run([
    "docker", "run", "-d",
    # No --gpus flag
    # No nvidia-container-runtime
    # No CUDA environment variables
    ...
])
```

**Impact:**
1. **Can't test ML/AI code:** Any repo that uses PyTorch, TensorFlow, or CUDA will fail in sandbox tests
2. **No GPU-accelerated testing:** Performance regression tests for GPU code are impossible
3. **No ML pipeline testing:** Agents can't validate model training, inference, or deployment code
4. **Competitive disadvantage:** As more repos incorporate ML, this gap grows

**Use cases that require GPU:**
- Testing ML model inference (PyTorch, TensorFlow, ONNX)
- Running GPU-accelerated data processing (RAPIDS, cuDF)
- Validating CUDA kernel code
- Testing ML CI/CD pipelines
- Running vision model evaluation (YOLO, Detectron2)
- NLP model testing (transformers, sentence-transformers)

**Competitor reference — Modal:**
```python
@app.function(
    sandbox=True,
    gpu="A100",  # GPU passthrough
    memory=32768,
)
def test_gpu_inference():
    import torch
    assert torch.cuda.is_available()
    model = load_model().to("cuda")
    result = model.infer(test_data)
    return result
```

Modal's GPU support:
- A100 (80GB) and H100 (80GB) GPUs
- Per-second billing for GPU time
- Automatic GPU driver management
- No cold start overhead for GPU initialization

**Fix options:**

**Option A — nvidia-docker runtime** (3-5 days):
```python
# In SandboxManager, add GPU support to the Docker run args
async def _create_env(self, session_id, image=None, *, gpu_request=None):
    docker_args = [
        "docker", "run", "-d",
        "--name", container_name,
    ]
    if gpu_request:
        docker_args.extend([
            "--gpus", f'"device={gpu_request.device_ids}"' if gpu_request.device_ids else "all",
            "--runtime", "nvidia",
            "-e", "NVIDIA_VISIBLE_DEVICES=all",
            "-e", "CUDA_VISIBLE_DEVICES=0",
        ])
    # ... rest of setup
```

**Configuration (per-role or per-spec):**
```yaml
# In agent role definition or JobSpec
sandbox:
  gpu:
    enabled: true
    count: 1
    memory: 16000  # MB
    model: "A100"  # Optional: specific GPU model
```

**Option B — GPU pool manager** (7-10 days, for SaaS):
- Manage a pool of GPU-enabled hosts
- Schedule GPU workloads across the pool
- Handle GPU contention (e.g., 2 agents requesting same GPU)
- Implement GPU time budgets and cost tracking

**Prerequisites:**
- `nvidia-docker` installed on host machines
- Docker runtime set to `nvidia` as default or per-container
- Host machines with NVIDIA GPUs

**Effort:** 3-5 days (Option A)

---

### 1.6 No gVisor or Firecracker Isolation

**Files involved:** Entire sandbox infrastructure

**What:** TestAI sandboxes run as standard Docker containers sharing the host Linux kernel. There is no microVM isolation (Firecracker), no user-space kernel (gVisor), and no hardware virtualization (Kata Containers). Every container has direct syscall access to the host kernel.

**Current architecture:**
```
┌──────────────────────────────────────────────┐
│  Host Machine                                │
│  ┌────────────────────────────────────────┐  │
│  │  Docker Daemon                         │  │
│  │  ┌──────────────┐  ┌──────────────┐   │  │
│  │  │ Sandbox-A    │  │ Sandbox-B    │   │  │
│  │  │ (Docker)     │  │ (Docker)     │   │  │
│  │  │              │  │              │   │  │
│  │  │ Shared Linux  │  │ Shared Linux │   │  │
│  │  │ Kernel        │  │ Kernel       │   │  │
│  │  │ Syscalls →    │  │ Syscalls →   │   │  │
│  │  │ Host Kernel   │  │ Host Kernel  │   │  │
│  │  └──────────────┘  └──────────────┘   │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

**Security implications of shared kernel:**
- A kernel 0-day in any syscall can escape all Docker containers
- `/proc` and `/sys` mounts can leak host information
- Shared kernel allows potential timing attacks between containers
- Container breakouts (CVE-2024-21626, CVE-2019-5736, etc.) affect all sandboxes
- `--privileged` mode (even if not used by TestAI) would give full host access

**Performance implications of current approach:**
- **Pro:** Fastest cold start (~1-3s for a full container)
- **Pro:** Lowest overhead (near-native compute, memory, I/O)
- **Con:** Weakest isolation boundary
- **Con:** No per-sandbox kernel tuning

**Competitor reference — Firecracker vs gVisor vs Docker:**

| Feature | Docker | gVisor | Firecracker |
|---------|--------|--------|-------------|
| Isolation type | Process (namespace) | Syscall interception | Hardware (KVM) |
| Boot time | ms | Sub-second | ~125-150ms |
| Overhead | Near-zero | 10-30% I/O | ~5% CPU |
| Kernel | Shared | Sentry (user-space) | Dedicated guest |
| GPU support | ✅ | ✅ | ❌ |
| Attack surface | Full syscall surface | ~50 syscalls | VM escape + KVM |
| Multi-tenant safe | ❌ | ⚠️ | ✅ |

**Fix options:**

**Option A — gVisor** (2-4 weeks):
```dockerfile
# Use gVisor's runsc runtime
docker run --runtime=runsc testai-sandbox
```

- Pros: Sub-second cold start, GPU support, good isolation
- Cons: 10-30% I/O overhead on heavy workloads, some syscalls not supported
- Best for: Compute-heavy AI workloads where full VM isn't justified

**Option B — Firecracker via Kata Containers** (4-6 weeks):
```yaml
# In docker-compose or container runtime config
runtime: io.containerd.kata.v2
```

- Pros: Hardware-level isolation, standard container API, Kubernetes-native
- Cons: ~200ms boot, no GPU support, more complex setup
- Best for: Regulated industries, multi-tenant, zero-trust environments

**Option C — Hybrid approach** (recommended for research, 2-3 days):
```python
# Per-sandbox isolation level based on data sensitivity
isolation_map = {
    "standard": "docker",       # Default for most workloads
    "sensitive": "gvisor",      # For private repos with sensitive data
    "maximum": "kata-containers",  # For regulated/PCI/HIPAA workloads
}

# Role-based isolation assignment
class SandboxScope:
    isolation_level: str = "standard"  # Configurable per-role
```

**Current assessment:** For single-tenant self-hosted deployments, Docker isolation is acceptable. For multi-tenant SaaS, gVisor or Kata Containers should be the default. This is a **medium-term investment** (not a critical gap today).

**Effort:** 2-3 days research + 2-4 weeks implementation

---

### Summary: Sandbox Isolation Comparison

| Feature | TestAI | E2B | Modal | Daytona | Tembo | Greptile |
|---------|--------|-----|-------|---------|-------|----------|
| Isolation type | Docker | Firecracker | gVisor | Docker | VM | Disposable |
| Per-subagent sandbox | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cold start | ~1-3s | ~150ms | Sub-second | 27-90ms | Seconds | ms |
| Network isolation | ❌ | ✅ 3 modes | ✅ | ✅ | ✅ | ✅ |
| GPU support | ❌ | ❌ | ✅ A100/H100 | ❌ | ❌ | ❌ |
| Max session | Configurable | 24h | Configurable | Unlimited | Session | Per-review |
| Worktree isolation | ❌ | N/A | N/A | N/A | N/A | N/A |

---

## 2. Subagent System

### 2.1 No Stuck Detector (CRITICAL)

**Files involved:** `backend/harness/agent/agent.py:907` (`_consecutive_same_tool`), `backend/harness/tools/subagent.py:994-1236` (spawn)

**What:** TestAI detects only ONE of the five known stuck-agent patterns. The other four patterns cause subagents to loop indefinitely, wasting tokens and time until the LLM eventually exceeds its context window limit or the hard timeout fires.

**Current implementation** (`backend/harness/agent/agent.py`, line 907):
```python
# The ONLY stuck detection in the entire codebase
if self._consecutive_same_tool >= 20:
    logger.warning("Tool loop detected: %s called %d times consecutively",
                    last_tool_name, self._consecutive_same_tool)
    return "[Error: Tool loop detected]"
```

This detects exactly one pattern: the same tool called 20+ times in a row. Everything else — repeating errors, infinite monologue, alternating ping-pong, context overflow — goes undetected.

**The 5 stuck patterns (OpenHands StuckDetector):**

| # | Pattern | Threshold | Detected? | Location |
|---|---------|-----------|-----------|----------|
| 1 | Repeating action-observation (same tool, same params) | 4+ consecutive | ✅ (20× threshold) | `agent.py:907` |
| 2 | Repeating action-error (tool keeps failing) | 3+ consecutive | ❌ | Nowhere |
| 3 | Agent monologue (long text with no tool calls) | 3+ consecutive | ❌ | Nowhere |
| 4 | Alternating ping-pong (A→B→A→B→A→B...) | 6+ alternating | ❌ | Nowhere |
| 5 | Context window overflow (token count nearing limit) | >90% of limit | ❌ | Nowhere |

**Why each pattern matters (with concrete examples):**

*Pattern 2 — Repeating tool errors:*
```python
# Current behavior: retries until max tool rounds
for attempt in range(3):
    result = await tool.execute()  # Fails every time
    if result.success:
        break
# No detection of "3 consecutive failures of same tool"
# Subagent burns 50 tool rounds on the same failing tool
```

Impact: A subagent that hits a persistent error (e.g., "file not found", "network timeout") will keep retrying 50 times, each time wasting an LLM call and tool execution. In the F12 findings, this exact pattern caused 10 zombie subagents that each made 50 tool calls before dying.

*Pattern 3 — Agent monologue:*
```python
# Agent outputs long text without calling any tool
"I think the issue is... let me consider... actually looking at this differently..."
# No tool calls for 3+ consecutive LLM responses
# No detection — agent loops until context window fills
```

Impact: The LLM gets stuck in a reasoning loop, generating thousands of tokens of "thinking" without making progress. This is especially common with weaker models or confusing prompts.

*Pattern 4 — Alternating ping-pong:*
```python
# Two tools called alternately in an infinite loop
Turn 1: read("file_a.py")
Turn 2: grep("pattern")  
Turn 3: read("file_a.py")  # Same as turn 1
Turn 4: grep("pattern")    # Same as turn 2
# 6+ alternating detections → stuck
```

Impact: The agent gets stuck in a "read one file, search, read again, search again" loop without making progress. Common when the LLM can't find what it's looking for.

*Pattern 5 — Context window overflow:*
```python
# Token count approaching limit with no resolution
token_count = len(tokenizer.encode(messages))
if token_count > 0.9 * max_tokens:
    # Should emit a warning and force a summary/compaction
    pass  # Currently nothing happens
```

Impact: The agent continues adding to the conversation until it hits the hard limit, at which point the LLM API returns a context_length_exceeded error. No graceful degradation, no compaction trigger.

**Competitor reference — OpenHands StuckDetector:**

```python
# From docs.openhands.dev/sdk/guides/agent-stuck-detector
class StuckDetector:
    REPEATING_ACTION_OBS: int = 4    # Same tool+params 4× in a row
    REPEATING_ACTION_ERR: int = 3    # Same tool error 3× in a row
    AGENT_MONOLOGUE: int = 3         # No tool calls for 3 turns
    PING_PONG: int = 6               # A→B→A→B alternating 6×
    CONTEXT_OVERFLOW: float = 0.9    # 90% of context window

    def detect(self, history: list[Turn]) -> StuckType | None:
        # Check all 5 patterns, return first hit
        ...
```

**Competitor reference — Claud Code:**
Claude Code uses a circuit-breaker-style approach with `consecutiveThreshold=20` (same as TestAI). From the oh-my-opencode research: `circuitBreaker.consecutiveThreshold=20`. So TestAI is at parity with Claude Code on Pattern 1, but behind OpenHands on the other 4.

**Fix: Implement a comprehensive StuckDetector** (2-3 days):

```python
# New class: backend/harness/agent/stuck_detector.py
from enum import Enum

class StuckType(Enum):
    REPEATING_TOOL = "repeating_tool"
    REPEATING_ERROR = "repeating_error"
    MONOLOGUE = "monologue"
    PING_PONG = "ping_pong"
    CONTEXT_OVERFLOW = "context_overflow"

class StuckDetector:
    """Detects 5 stuck-agent patterns. Thread-safe, zero deps on LLM."""
    
    REPEATING_TOOL_THRESHOLD = 4      # Same tool name + input
    REPEATING_ERROR_THRESHOLD = 3     # Same error from same tool
    MONOLOGUE_THRESHOLD = 3           # No tool calls in N turns
    PING_PONG_THRESHOLD = 6           # A→B→A→B alternating
    CONTEXT_OVERFLOW_RATIO = 0.9      # 90% of max context
    
    def __init__(self):
        self._tool_history: list[tuple[str, str]] = []
        self._error_history: list[tuple[str, str]] = []
        self._tool_call_turns: list[bool] = []
    
    def record_turn(self, tool_calls: list[dict], errors: list[tuple[str, str]], 
                    token_count: int, max_tokens: int) -> StuckType | None:
        """Record one agent turn. Returns StuckType if stuck, None otherwise."""
        
        # Pattern 1: Repeating tool
        if self._check_repeating_tool(tool_calls):
            return StuckType.REPEATING_TOOL
        
        # Pattern 2: Repeating errors
        if self._check_repeating_errors(errors):
            return StuckType.REPEATING_ERROR
        
        # Pattern 3: Monologue
        self._tool_call_turns.append(len(tool_calls) > 0)
        if len(self._tool_call_turns) >= self.MONOLOGUE_THRESHOLD:
            if not any(self._tool_call_turns[-self.MONOLOGUE_THRESHOLD:]):
                return StuckType.MONOLOGUE
        
        # Pattern 4: Ping-pong
        if self._check_ping_pong(tool_calls):
            return StuckType.PING_PONG
        
        # Pattern 5: Context overflow
        if max_tokens > 0 and token_count / max_tokens >= self.CONTEXT_OVERFLOW_RATIO:
            return StuckType.CONTEXT_OVERFLOW
        
        return None
```

**Integration into agent.py:**
```python
# In the agent's main loop (around line 839-928)
self._stuck_detector = StuckDetector()

# After each turn:
stuck = self._stuck_detector.record_turn(
    tool_calls=tool_calls,
    errors=tool_errors,
    token_count=current_token_count,
    max_tokens=self.max_tokens,
)
if stuck is not None:
    await self._event_bus.emit(ErrorEvent(
        message=f"Subagent stuck: {stuck.value}",
        recoverable=False,
        category="stuck",
        session_id=self.session_id,
        agent_id=self.agent_id,
    ))
    return f"[Stuck: {stuck.value}]"
```

**Effort:** 2-3 days

---

### 2.2 ~~No Heartbeat Monitoring~~ ✅ IMPLEMENTED

**Status:** `SubagentHeartbeat` is fully implemented at `backend/harness/services/heartbeat.py` (347 lines), wired into `delegate_task.py:811-819` (parallel heartbeat task with asyncio.wait), and covered by `tests/test_heartbeat.py` (~16 test cases). Uses Hermes-pattern idle (30s) vs in-tool (5min) stale thresholds, progressive stale warnings, and EventBus heartbeat events for dashboard observability.

---

### 2.3 No Hard Timeout Per Subagent

**Files involved:** `backend/harness/tools/subagent.py:1197` (`_call_child_with_enhancements`)

**What:** There is no per-subagent hard timeout. The circuit breaker has a recovery timeout (30s), and the budget tracker has a soft cap, but neither is a per-subagent maximum execution timeout. A subagent can run indefinitely as long as it stays within the circuit breaker's error rate threshold.

**Current behavior:**
```python
# subagent.py:1197
result_inner = await _call_child_with_enhancements(
    _run_child,
    subagent_id=subagent_id,
    model=model_override,
    breaker=breaker,
)
# No timeout parameter!
# _call_child_with_enhancements doesn't enforce a max wall-clock time
```

**Impact:**
1. **Runaway subagent:** A subagent can run for hours, burning tokens and budget
2. **No predictability:** Can't estimate how long a job will take
3. **Resource leak:** If the parent is cancelled, the subagent continues running (orphan)
4. **Dashboard stuck:** The job shows "running" indefinitely

**Competitor reference — Hermes hard timeout:**
```python
# Hermes delegates to ThreadPoolExecutor with timeout
_child_future = _timeout_executor.submit(_run_with_thread_capture)
try:
    result = _child_future.result(timeout=child_timeout)  # Hard timeout!
except FuturesTimeoutError:
    if hasattr(child, "interrupt"):
        child.interrupt()
    if child_api_calls == 0:
        diagnostic_path = _dump_subagent_timeout_diagnostic(...)
    raise
```

**Fix: Add per-subagent timeout** (2-3 days):
```python
# Option A: asyncio.wait_for
async def spawn(self, goal, *, timeout=300, ...):
    try:
        result = await asyncio.wait_for(
            child.run(goal),
            timeout=timeout,
        )
        return result
    except asyncio.TimeoutError:
        await self._event_bus.emit(ErrorEvent(
            message=f"Subagent {subagent_id} timed out after {timeout}s",
            recoverable=False,
            category="timeout",
        ))
        return SubagentResult(
            subagent_id=subagent_id,
            status="error",
            error=f"timeout_after_{timeout}s",
        )

# Option B: Configurable per-role
# In Role YAML:
#   timeout_seconds: 300  (coordinator)
#   timeout_seconds: 120  (explore)
```

**Effort:** 2-3 days

---

### 2.4 No 0-API-Call Diagnostics for Stuck Subagents

**Files involved:** `backend/harness/tools/subagent.py:1197`

**What:** When a subagent is stuck before making any API call (e.g., provider unreachable, auth failure, configuration error), the system has no diagnostic capability. It can't distinguish "subagent is thinking" from "subagent is stuck before the first LLM call."

**Impact:**
1. **Black box debugging:** When a subagent fails with 0 API calls, there's no diagnostic data
2. **Configuration errors invisible:** Wrong API key, endpoint, model — all produce the same generic error
3. **Wasted retries:** System may retry a subagent that can never succeed (bad config)
4. **No root cause:** Ops can't tell if it's code bug, infra issue, or config error

**Competitor reference — Hermes:**
```python
# Hermes captures diagnostic when subagent times out with 0 API calls
if child_api_calls == 0:
    diagnostic_path = _dump_subagent_timeout_diagnostic(
        subagent_id=subagent_id,
        session_dir=child.session_dir,
    )
    # Includes: full config, provider endpoint, last N log lines,
    # Python thread stack, env vars (redacted)
```

**Fix: Implement 0-API-call diagnostic** (2-3 days):
```python
# In subagent.py:spawn()
async def spawn(self, goal, ...):
    child = self._agent_factory(system_prompt, ...)
    api_call_count = 0
    
    original_run = child.run
    async def tracked_run(*args, **kwargs):
        nonlocal api_call_count
        result = await original_run(*args, **kwargs)
        api_call_count = getattr(child, "_api_call_count", 0)
        return result
    child.run = tracked_run
    
    try:
        result = await asyncio.wait_for(child.run(goal), timeout=timeout)
        return result
    except (asyncio.TimeoutError, Exception) as exc:
        if api_call_count == 0:
            diagnostic = {
                "subagent_id": subagent_id,
                "goal_preview": goal[:200],
                "model": model_override or "default",
                "provider": getattr(child, "_provider", "unknown"),
                "api_call_count": 0,
                "error": str(exc),
                "system_prompt_preview": system_prompt[:500],
                "toolsets": toolsets,
                "timestamp": time.time(),
            }
            logger.error("SUBAGENT_0_API_CALLS %s", json.dumps(diagnostic))
        raise
```

**Effort:** 2-3 days

---

### 2.5 No Context Modes (Isolated vs Fork)

**Files involved:** `backend/harness/tools/subagent.py:1142-1149`

**What:** Every subagent gets a freshly built system prompt with no access to parent conversation context. No "fork" mode exists where a subagent inherits parent's conversation history.

**Current implementation:**
```python
system_prompt = await _build_child_system_prompt(
    goal=goal,
    context=context,  # Only caller-provided context string
    role=role,
)
# No parent conversation history included
```

**Impact:**
1. **Context duplication:** Explore subagent re-reads files the parent already read
2. **Lost context:** Parent's discoveries (e.g., "bug is in auth.py") don't propagate
3. **Redundant work:** Each subagent starts from scratch
4. **Wasted tokens:** Rediscovering what parent already found

**Competitor reference — OpenClaw context modes:**
```python
# Mode 1: Isolated (default) — Fresh context, lower tokens
sessions_spawn({task: "...", context: "isolated"})

# Mode 2: Fork — Branched from parent transcript
sessions_spawn({task: "...", context: "fork"})
# Child gets parent's conversation history
```

**Fix: Add context_mode parameter** (2-3 days):
```python
async def spawn(self, goal, *, context_mode="isolated", ...):
    if context_mode == "fork" and parent_session_id:
        parent_messages = await load_session_messages(parent_session_id)
        compressed = compress_context(parent_messages, max_tokens=4000)
        context = (
            f"Parent conversation context:\n{compressed}\n\n"
            f"Your goal: {goal}"
        )
    else:
        context = goal
```

**Effort:** 2-3 days

---

### 2.6 No Push-Based Completion

**Files involved:** `backend/harness/tools/subagent.py:921-927`

**What:** All spawn variants block until complete. There's no true fire-and-forget with push-based result delivery.

**Current behavior:**
```python
result = await self.spawn(goal, ...)    # Blocks!
results = await self.spawn_many(goals)  # Gathers all blocks!
```

**Competitor reference — OpenClaw:**
```python
const runId = sessions_spawn({task: "..."});
// Returns immediately
// Completion arrives as internal event
// Retry with exponential backoff if delivery fails
// Idempotency keys for exactly-once delivery
```

**Fix: Push-based completion** (3-5 days):
```python
async def spawn_push(self, goal, *, on_completed=None):
    subagent_id = f"sa-push-{uuid.uuid4().hex[:8]}"
    if on_completed:
        self._completion_callbacks[subagent_id] = on_completed
    asyncio.create_task(self._run_push(subagent_id, goal))
    return subagent_id  # Return immediately!
```

**Effort:** 3-5 days

---

### 2.7 No Subagent-Level Resume

**Files involved:** `backend/harness/services/job_checkpoint.py`

**What:** C08 pause/resume works at job level only. A failed subagent must restart from scratch — no subagent-level checkpointing.

**Current behavior:**
```python
# On failure, no checkpoint data — must re-spawn from turn 1
return SubagentResult(subagent_id=..., status="error", ...)
```

**Competitor reference — Devin:** Allows resuming cancelled/failed agents.
**Competitor reference — Anthropic:** Uses `claude-progress.txt` as structured artifact for cross-session handoff.

**Fix: Subagent checkpointing** (3-5 days):
```python
async def _checkpoint_subagent(subagent_id, messages, tool_results):
    checkpoint = {
        "subagent_id": subagent_id,
        "message_count": len(messages),
        "last_tool": tool_results[-1] if tool_results else None,
        "completed_goals": [],
        "timestamp": time.time(),
    }
    await save_checkpoint(f"subagent:{subagent_id}", checkpoint)
```

**Effort:** 3-5 days

---

### 2.8 Goal Decomposition Hallucination (F6)

**Files involved:** `backend/harness/tools/orchestrator_tool.py:1-56` (`_llm_decompose`)

**What:** The LLM-driven `_llm_decompose` sometimes produces kanban task graphs unrelated to the user prompt. Observed: prompt "PR 37724 cache_version" → tasks about "fix unhashable type: slice".

**Root cause:** The decomposition prompt passes system prompt + user goal. LLM response fragments include hallucinated content before the JSON boundary.

**Impact:** Wrong work, wasted budget, user confusion, actual bug unfixed.

**Fix: Entity sanity check** (1 day):
```python
def _validate_decomposition(prompt: str, tasks: list[dict]) -> list[dict]:
    entities = set()
    entities.update(re.findall(r'PR\s*#?(\d+)', prompt))
    entities.update(re.findall(r'(\w+(?:\(\))?)', prompt))
    entities.update(re.findall(r'[\w/]+\.\w+', prompt))
    entities.update(re.findall(r"'([^']+)'", prompt))
    
    valid = [t for t in tasks 
             if any(e.lower() in (t.get("title","")+t.get("description","")).lower() 
                    for e in entities if len(e) > 2)]
    return valid or tasks  # Fallback to original if all filtered
```

**Effort:** 1 day

---

### 2.9 Session Status Leak — Zombie Subagents (F5)

**Files involved:** `backend/harness/tools/subagent.py`, `backend/harness/store/adapters/postgres.py`

**What:** When subagents complete or fail, their session rows in the `sessions` table remain `status="running"` forever. There is no code that transitions subagent session status to `completed` or `failed`.

**Observed in F5 (June 24 e2e run):**
```
10 sessions all status="running"
Even after result_summary set to error, session row never reached terminal state
```

**Impact:**
1. Dashboard shows ever-increasing "active subagents" count
2. Can't distinguish active from completed subagents by DB query
3. No cleanup trigger for zombie sessions
4. Session-based billing counts completed sessions as active

**Root cause:** The `kanban_service` has `sweep_orphan_in_progress` for kanban tasks but there's no equivalent for `sessions`.

**Fix: Add session status transition** (1-2 days):
```python
# In subagent.py, after spawn completes (success or failure):
async def _finalize_session(subagent_id, status, result):
    await db.execute(
        "UPDATE sessions SET status=$1, finished_at=$2, result_summary=$3 "
        "WHERE session_id=$4",
        status, time.time(), json.dumps(result), subagent_id,
    )

# Add a session reaper (like kanban's sweep_orphan_in_progress):
async def sweep_orphan_sessions(max_age_seconds=3600):
    """Mark sessions stuck in 'running' for too long as 'orphaned'."""
    await db.execute(
        "UPDATE sessions SET status='orphaned' "
        "WHERE status='running' AND started_at < NOW() - $1::interval",
        f"{max_age_seconds} seconds",
    )
```

**Effort:** 1-2 days

---

## 3. Knowledge Graph & Memory

### 3.1 ~~No Semantic Triple Extraction~~ ✅ RESOLVED

**Resolution date:** 2026-06-25
**Rationale:** CodeGraph already provides all semantic relationships the gap describes. No LLM-based extraction needed.

**What was requested:** Extract `(subject, predicate, object)` triples from code (e.g. `(UserService.login) --[calls]--> (AuthService.validate_token)`) via LLM-based extraction into the Postgres `kg_edges` table.

**Why it's already solved:** The codebase has **two separate knowledge graph systems**, and the one agents actually use already provides caller/callee/dependency analysis via AST parsing — no LLM needed.

| System | Data source | Used by agents? | Relationships |
|--------|------------|-----------------|---------------|
| **CodeGraph** (`codegraph_*` tools) | AST-parsed SQLite index | ✅ Yes — `codegraph_explore`, `codegraph_search`, `codegraph_callers`, `codegraph_callees` | callers, callees, imports, extends, implements (deterministic) |
| **Postgres `kg_edges`** (`L1Indexer`) | File co-occurrence from agent runs | ❌ No — dashboard only | `co_occurs_in_run` (weak signal) |

**CodeGraph already provides (files: `knowledge_graph_tool.py`, `codegraph_tools.py`):**
- `codegraph_callers(symbol)` → "what calls this function?" (exact AST match)
- `codegraph_callees(symbol)` → "what does this function call?"
- `codegraph_search(query)` → find symbols by name
- `codegraph_explore(query)` → free-form: source + relationship map + blast radius
- `codegraph node(symbol)` → full source + caller/callee trail

**Why LLM triple extraction is inferior:**

| | LLM triples (G3 proposed) | CodeGraph (existing) |
|-|---------------------------|---------------------|
| Speed | Seconds per file (LLM call) | Milliseconds (SQLite query) |
| Cost | Token cost per extraction | Zero |
| Accuracy | Hallucination-prone | Deterministic (AST-based) |
| Coverage | Only files agent touches | Entire repo indexed |
| Staleness | Re-extract on every run | Incremental sync |

**What actually needs improvement (separate from G3):**
The Postgres `kg_edges` table (used by the dashboard's Louvain community detection) stores weak co-occurrence edges. It could be improved by pulling real structural relationships from CodeGraph, but this is a dashboard polish task (~2-3 days), not a 5-7 day semantic extraction project.

**Greptile comparison:** Greptile's "semantic code graph" is a pre-built AST-level structural index — the same approach as CodeGraph. TestAI already has this capability via the CodeGraph CLI integration.

**Effort saved:** 5-7 days (no longer needed)

---

### 3.2 KG Never Updated After Fixes Are Applied

**Files involved:** `backend/harness/services/artifact_store.py`, `backend/harness/tools/knowledge_graph_tool.py`

**What:** The Knowledge Graph is built once at the start of a run (via `L1Indexer.promote()`) and never updated after the agent fixes code, adds tests, or generates artifacts. Subsequent agents in the same run work with stale graph data.

**Current flow:**
```
1. Orchestrator starts
2. Clone repo → Build KG (L1Indexer.promote())  ← Once at beginning
3. Explore subagents run (query stale KG)
4. Fix subagents run (modify code, add tests)
5. ⚠️ KG is NOT updated with the changes!
6. Review subagents run (query stale KG)
7. Next run starts → KG rebuilt from scratch
```

**Impact:**
1. **Stale context:** Review subagents don't see what fix subagents changed
2. **No incremental learning:** The KG doesn't capture "what was fixed" or "what was tested"
3. **Cross-subagent blindness:** Subagent B can't query "what did subagent A change?"
4. **Repeated exploration:** Each run rebuilds the KG from scratch — no persistence of learned relationships

**Fix options:**

**Option A — Incremental KG updates** (3-5 days):
```python
# After every write_file or edit tool call, update the KG
async def _on_file_modified(file_path: str, session_id: str):
    """Update KG when an agent modifies a file."""
    # Re-extract symbols from modified file
    symbols = await codegraph_extract_symbols(file_path)
    # Update kg_nodes for new/modified symbols
    for sym in symbols:
        upsert_kg_node(
            name=sym.name,
            kind=sym.kind,
            file_path=file_path,
            session_id=session_id,
        )
    # Re-compute edges for affected files
    affected_files = await get_related_files(file_path)
    for affected in affected_files:
        upsert_kg_edge(
            source=file_path,
            target=affected,
            relation="co_occurs_in_run",
        )
```

**Option B — End-of-subagent KG sync** (2-3 days, simpler):
```python
# In subagent.py, after spawn completes:
async def _sync_subagent_kg(subagent_id, session_id):
    """Sync KG with changes made by this subagent."""
    modified_files = await get_modified_files(subagent_id)
    if not modified_files:
        return
    # Promote modified files through L1Indexer
    await L1Indexer(session_id).promote(files=modified_files)
```

**Effort:** 2-3 days (Option B)

---

### 3.3 No Cross-Run Memory Curation (L2 Curated Lessons)

**Files involved:** `reference/hermes-agent/tools/memory_tool.py` (L0/L1), `backend/harness/services/` (L2?)

**What:** The memory system has three tiers (L0 raw artifacts, L1 indexed facts, L2 curated lessons) but L2 is essentially unimplemented. There's no mechanism to:
- Auto-curate lessons from completed runs
- Extract "what worked / what didn't" patterns
- Persist cross-run improvements
- Share learnings between runs

**Current L2 state:**
```python
# Memory tool exists for basic text storage
memory.add(target="memory", content="The auth module uses JWT tokens")
memory.add(target="memory", content="Test suite takes 45s to run")

# But there's no:
# - Auto-extraction of lessons from run outcomes
# - Deduplication of similar lessons
# - Prioritization/ranking of lessons
# - Cross-session sharing
```

**Impact:**
1. **No learning:** Each run starts with zero context from previous runs
2. **Repeated mistakes:** If a subagent discovered "don't use pytest-xdist with this project", the next run won't know
3. **No improvement curve:** The system doesn't get better at fixing code over time
4. **Tribal knowledge lost:** What the first run learned is gone when the second run starts

**Competitor reference — Anthropic cross-run memory:**

Anthropic's long-running agent pattern uses `claude-progress.txt` — a structured file that persists across sessions:
```json
{
  "features": [
    {"description": "User can log in", "passes": true, "last_tested": "2025-11-26"},
    {"description": "User can reset password", "passes": false, "last_tested": "2025-11-25"}
  ],
  "lessons": [
    "Use Puppeteer MCP for browser testing — curl misses JS-rendered content",
    "Always run `npm run build` before testing to catch compilation errors"
  ]
}
```

**Fix: Implement L2 lesson curation** (5-7 days):

```python
# Phase 1: End-of-run lesson extraction
async def _extract_lessons(run_id, session_id, outcome):
    """Extract lessons from a completed run."""
    # Gather data:
    events = await get_stream_events(session_id)
    errors = [e for e in events if e.type == "error"]
    successes = [e for e in events if e.type == "tool.execution.completed" and e.payload.get("success")]
    
    prompt = f"""Analyze this run and extract 3-5 reusable lessons.
    
Run outcome: {outcome.status}
Errors encountered: {len(errors)}
Tools used: {len(successes)}
Repository: {outcome.repo_url}
Goal: {outcome.goal}

Extract lessons as JSON array:
[{{"lesson": "...", "category": "tool|code|process|env", "priority": "high|medium|low"}}]
"""
    lessons = await llm.chat(prompt)
    return json.loads(lessons)

# Phase 2: Cross-run lesson store
async def get_relevant_lessons(repo_url: str, goal: str, limit=5):
    """Retrieve top-k lessons relevant to this repo/goal."""
    rows = await db.fetch(
        "SELECT lesson, category, priority FROM curated_lessons "
        "WHERE repo_url=$1 ORDER BY priority DESC, created_at DESC LIMIT $2",
        repo_url, limit,
    )
    return [row["lesson"] for row in rows]
```

**Effort:** 5-7 days

---

### 3.4 ~~No Automatic Compaction Agent~~ ✅ RESOLVED

**Resolution date:** 2026-06-25
**Rationale:** The `ContextCompressor` already implements auto-compaction at 85% context threshold — functionally equivalent to what a "compaction agent" would do, without the added complexity.

**What was requested:** An autonomous subagent that decides when/how to compact context.

**Why it's already solved:** The `ContextCompressor` (`context_compressor/compressor.py`, 605 lines) implements:
- Auto-compaction at 85% context threshold
- Iterative summary updates (not just truncation)
- Anti-thrashing counters (prevents compact→expand→compact loops)
- Focus-topic preservation (user-specified topics get higher summary budget)
- Three strategies: micro-compact (free, strip old tool outputs), auto-compact (LLM summary), reactive compact (on API error)

The compressor is wired into the agent loop at `agent.py:824-831` and fires automatically. An "autonomous agent" that proactively compacts would add latency and cost for marginal quality improvement over the existing threshold-based approach.

**Files:** `harness/context_compressor/compressor.py`, `harness/context_compressor/summary.py`, `harness/compaction.py`

**Effort saved:** 3-5 days (no longer needed)

---

### 3.5 No Per-Subagent Memory Isolation

**Files involved:** `reference/hermes-agent/tools/memory_tool.py` (global)

**What:** The memory tool operates on global MEMORY.md / USER.md files. There is no per-subagent memory isolation. Subagent A's memories are visible to Subagent B.

**Current behavior:**
```python
# Subagent A writes to memory:
memory.add("memory", "Found bug in auth.py: missing JWT validation")

# Subagent B reads the same memory:
entries = memory.list("memory")  # ← Sees A's entries too!
```

**Impact:**
1. **Context pollution:** Subagents see irrelevant memories from other subagents
2. **Information leakage:** Subagent A's findings about a security bug are visible to all
3. **Memory clutter:** Cross-run memory fills with entries from unrelated tasks
4. **No scope boundaries:** Can't isolate "explore agent memories" from "fix agent memories"

**Fix: Add scope-based memory isolation** (2-3 days):

```python
# Option A: Per-subagent memory files
MEMORY_FILE = f"/workspace/.memory/{subagent_id}/MEMORY.md"
USER_FILE = f"/workspace/.memory/{subagent_id}/USER.md"

# Option B: Scoped entries with session_id tag
class ScopedMemory(MemoryTool):
    def add(self, target, content, scope=None):
        scope = scope or self.session_id
        content = f"[{scope}] {content}"  # Tag with scope
        super().add(target, content)
    
    def list(self, target, scope=None):
        entries = super().list(target)
        if scope:
            return [e for e in entries if e.startswith(f"[{scope}]")]
        return entries
```

**Effort:** 2-3 days

---

### 3.6 Memory Tool Limited to Text-Only Entries

**Files involved:** `reference/hermes-agent/tools/memory_tool.py`

**What:** The memory tool stores flat text entries with character limits (2200 for memory, 1375 for user). There's no support for structured data, code snippets, test results, or file references.

**Current schema:**
```python
# Each entry is a plain string
self.memory_entries: List[str] = []
# No metadata, no type field, no timestamps, no source tracking
```

**Impact:**
1. **No structured memory:** Can't store "test_result: pass/fail" as structured data
2. **No file references:** Can't say "see /workspace/tests/test_auth.py for details"
3. **No timestamps:** Can't tell when a memory was added
4. **No source tracking:** Can't tell which subagent/run added which memory
5. **No prioritization:** All entries are equal — no way to mark important vs trivial

**Competitor reference — LangGraph programmable memory:**
LangGraph offers multiple memory types: buffer, summary, vector, entity, graph — each with structured schemas.

**Fix: Add structured memory entries** (3-5 days):

```python
@dataclass
class MemoryEntry:
    content: str
    type: Literal["observation", "lesson", "decision", "fact", "warning"]
    source: str  # subagent_id or session_id
    timestamp: float
    priority: Literal["high", "medium", "low"]
    file_refs: list[str]  # Related file paths
    metadata: dict  # Extensible

class StructuredMemory(MemoryTool):
    def add(self, entry: MemoryEntry):
        serialized = self._serialize(entry)
        entries = self._entries_for("memory")
        entries.append(serialized)
        self.save_to_disk("memory")
    
    def query(self, type=None, source=None, priority=None, file_ref=None):
        """Query memory entries with filters."""
        entries = self._deserialize_all()
        if type:
            entries = [e for e in entries if e.type == type]
        if source:
            entries = [e for e in entries if e.source == source]
        if file_ref:
            entries = [e for e in entries if file_ref in e.file_refs]
        return entries
```

**Effort:** 3-5 days

---

## 4. Observability & Events

### 4.1 No OpenTelemetry Export

**Files involved:** `backend/harness/events.py` (EventBus), `backend/api/routers/events.py`

**What:** The event bus has 4 sinks (trace_callback, event_source, log, stream_events_db) but no OpenTelemetry exporter. The wire names (`tool.execution.started`, `llmcall.started`, `agent.completed`) intentionally align with OTel GenAI semantic conventions (opentelemetry.io/docs/specs/semconv/gen-ai), but no actual OTel spans are created. This means TestAI cannot integrate with enterprise observability stacks (Datadog, Grafana, Honeycomb, SigNoz).

**Current sinks** (`events.py:EventBus`):
```python
sinks = [
    trace_callback,    # In-memory callback
    event_source,      # SSE for live UI
    log,               # Python logger
    stream_events_db,  # Postgres stream_events table
]
```

**2026 context — Microsoft Agent Framework (BUILD 2026):**
> "OpenTelemetryAgent: automatic OpenTelemetry Semantic Conventions tracing" — ships as a built-in agent observer in the MAF harness. OTel traces flow into Application Insights with zero extra wiring. This is now the industry baseline expectation for any production agent harness.

**2026 context — Modern Agent Harness Blueprint (March 2026):**
The blueprint places "Typed Event Bus → Tracing / Metrics / Replay / Eval Harness" as a core architectural layer. OTel export is the expected integration point. The blueprint explicitly warns: "without OTel, you cannot do production debugging across distributed agent runs."

**Fix: Add OTel exporter as 5th sink** (3-5 days):
```python
# backend/harness/observability/otel_exporter.py
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

class OTelEventSink:
    SPAN_MAP = {
        "tool.execution.started": ("tool.execution", "tool"),
        "llmcall.started": ("llm.call", "llm"),
        "subagent.spawned": ("subagent", "subagent"),
        "agent.started": ("agent.run", "agent"),
    }
    
    async def emit(self, event):
        wire_name = wire_name(event)
        if wire_name in self.SPAN_MAP:
            span_name, _ = self.SPAN_MAP[wire_name]
            tracer = trace.get_tracer("testai")
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("event.type", wire_name)
                span.set_attribute("session_id", event.session_id or "")
                span.set_attribute("agent_id", event.agent_id or "")
                if hasattr(event, "duration_ms"):
                    span.set_attribute("duration_ms", event.duration_ms)
                if hasattr(event, "error"):
                    span.set_status(Status(StatusCode.ERROR, event.error))
```

**Effort:** 3-5 days

---

### 4.2 No Per-Tool Latency Metrics (p50/p95)

**Files involved:** `backend/harness/core/events.py` (ToolExecutionCompleted), `backend/api/routers/events.py` (_aggregations)

**What:** `ToolExecutionCompleted` carries no `duration_ms` field. The `_aggregations` endpoint derives duration from `created_at` deltas (imprecise, drifts across clock skew). No per-tool p50/p95 latency — the minimum viable performance metric for production debugging.

**2026 context — Context Engineering guide (Feb 2026):**
> "Production agents consume roughly 100 input tokens per 1 output token. An unconstrained software-engineering agent runs $5–8 per task." Without per-tool latency tracking, you cannot identify which tools are the cost bottlenecks. The guide recommends instrumenting every tool call with `started_at` and `ended_at`.

**Fix: Add duration_ms to ToolExecutionCompleted** (1-2 days):
```python
@dataclass
class ToolExecutionCompleted:
    tool_name: str
    result: str
    duration_ms: float  # NEW
    session_id: str = ""
    agent_id: str = ""
```

**Effort:** 1-2 days

---

### 4.3 No Cancel/Interrupt Event Type

**Files involved:** `backend/harness/core/events.py`, `backend/harness/services/cancel_watcher.py`

**What:** Cancel/pause emits string-typed stream events. No typed event class for downstream consumers.

**2026 context — A2A Protocol v1.0 (Google, June 2026):**
Defines `TaskStatusUpdateEvent` with explicit states: `CANCELED`, `INPUT_REQUIRED`, `AUTH_REQUIRED` — cancellation is a first-class typed event.

**Fix: Add typed interrupt/cancel events** (2-3 days):
```python
@dataclass
class AgentCancelled:
    reason: str
    triggered_by: str  # "user" | "system" | "timeout"
    session_id: str = ""
    agent_id: str = ""
```

**Effort:** 2-3 days

---

### 4.4 No Live Tool Output Streaming to Sandbox UI

**Files involved:** `backend/harness/tools/docker_executor.py`, `src/app/(dashboard)/sandbox/[sessionId]/`

**What:** Sandbox page shows metadata only — no real-time terminal output from running subagents.

**2026 context — Greptile TREX:** Multi-modal artifact streaming — screenshots, logs, API traces, execution scripts, video. Every artifact is verifiable.
**2026 context — Daytona:** Interactive PTY terminal sessions with full display control.

**Fix: Add WebSocket-based live terminal** (3-5 days)

**Effort:** 3-5 days

---

### 4.5 No Pipeline-Store Dead Component Cleanup (F27)

**Files involved:** 10+ frontend files using stale pipeline-store architecture

**What:** Prototype commit introduced pipeline-store with stale event names (`tool:start`, `tool:end`). New orchestrator emits `tool.execution.started` / `tool.execution.completed`. Dead components receive zero events silently.

**Fix: Remove dead components** (2-3 days)

**Effort:** 2-3 days

---

## 5. Entry Points & User-Facing Gaps

### 5.1 Three Entry Points, No Clear Default

**Files involved:** `backend/harness/orchestrator.py` — `run_single()`, `run_multi()`, `run_job_spec()`

**What:** The orchestrator exposes three distinct entry points with overlapping responsibilities and no guidance on which to use:

- `run_single()` — undocumented, no tests, used internally by `run_job_spec`
- `run_multi()` — single caller, no tests, likely dead code
- `run_job_spec()` — primary entry point with full spec/tier/capability support

```python
class OrchestratorEngine:
    async def run_single(self, run_id, session_id, repo_url, goal, ...): ...
    async def run_multi(self, specs: list[dict], ...): ...  # 1 caller, 0 tests
    async def run_job_spec(self, spec: JobSpec, ...): ...  # Primary
```

**2026 context — Modern Agent Harness Blueprint (March 2026):**
Recommends a single `run(spec: RunSpec)` entry point with optional fields:
```typescript
run({
    spec_id?: string,
    run_id: string,
    prompt: string,
    repo_url?: string,
    // Everything else optional with sensible defaults
})
```

**Fix: Consolidate to 2 entry points** (2-3 days):
```python
class OrchestratorEngine:
    async def run_job_spec(self, spec: JobSpec, ...) -> dict:
        """Primary entry point. Full pipeline."""
        
    async def run_repo(self, repo_url: str, goal: str, ...) -> dict:
        """Lightweight entry point. Creates minimal JobSpec internally."""
        spec = JobSpec(prompt=goal, repo_url=repo_url, tier=1)
        return await self.run_job_spec(spec)
    
    # Deprecate run_multi and run_single as public entry points
```

**Effort:** 2-3 days

---

### 5.2 No GitHub Issues/PRs Integration

**Files involved:** None — entirely missing feature

**What:** No mechanism to fetch GitHub Issues/PRs, present them for user selection, or post results back.

**Current flow:** User provides repo URL + prompt → clone → explore → try to figure out what to do
**Desired flow:** User provides repo URL → fetch Issues/PRs → user selects → fulfill → post results back

**2026 context — GitHub Copilot Agent Tasks API (June 2026):**
> "POST /agents/repos/{owner}/{repo}/tasks endpoint that triggers the cloud coding agent from any script, portal, or CI pipeline. The agent runs in a GitHub Actions environment, opens a PR when done, and supports mid-task clarification."

**2026 context — GitHub Agent Apps (June 2026):**
> "Three entry points: assign an issue to the agent, @mention it in a pull request comment, or select it in the Agents UI with a custom prompt."

**Fix: Add GitHub API integration** (5-7 days):
```python
class GitHubIntegration:
    async def list_issues(self, repo_url, state="open", limit=20):
        """Fetch open issues."""
        
    async def list_prs(self, repo_url, state="open", limit=20):
        """Fetch open PRs."""
        
    async def post_pr_comment(self, repo_url, pr_number, body):
        """Post comment on PR."""
        
    async def create_run_from_issue(self, repo_url, issue_number) -> JobSpec:
        """Create JobSpec from a GitHub issue."""
```

**Effort:** 5-7 days

---

### 5.3 No Session-Aware Chat Agent

**Files involved:** None — entirely missing capability

**What:** The chat agent has no tools to query session history. Cannot answer "what happened in the last run?" or "is PR #123 still being worked on?"

**Data available but not exposed to the agent:**
- `sessions` table: status, goal, model, duration, tokens
- `stream_events` table: per-session event log
- `job_specs` table: spec status, tier, prompt
- `kanban_tasks` table: task progress

**2026 context — GitHub Copilot Memory++ (BUILD 2026):**
> "Memory++ and /chronicle provide cross-surface continuity — your entire Copilot session history now syncs across the app, CLI, VS Code, JetBrains, and GitHub.com."

**Fix: Add session_query tool** (3-5 days):
```python
class SessionQueryTool(BaseTool):
    async def call(self, query: str, filters: dict = None) -> str:
        """Query session history with filters."""
        conditions = []
        if filters.get("repo_url"):
            conditions.append(f"repo_url = '{filters['repo_url']}'")
        if filters.get("status"):
            conditions.append(f"status = '{filters['status']}'")
        
        rows = await db.fetch(f"""
            SELECT session_id, status, goal, model,
                   duration_sec, prompt_tokens, created_at
            FROM sessions WHERE {' AND '.join(conditions) or 'TRUE'}
            ORDER BY created_at DESC LIMIT 10
        """)
        return json.dumps([dict(r) for r in rows], default=str)
```

**Effort:** 3-5 days

---

### 5.4 No User-Configurable Sandbox Customization

**Files involved:** `backend/harness/sandbox/sandbox_scope.py`, `backend/api/routers/settings.py`

**What:** Sandbox configuration is mostly env vars. Users cannot configure resource limits, pre-installed tools, startup scripts, or network isolation from the UI.

**Current:**
```python
DEFAULT_IMAGE = os.environ.get("SANDBOX_IMAGE", "nikolaik/python-nodejs")
```

**2026 context — Tembo:** 5 sandbox sizes (Micro→Ultra) with configurable CPU/memory/disk.
**2026 context — Daytona:** Fully configurable via YAML.

**Fix: Add sandbox config to Settings API** (2-3 days):
```python
@router.get("/api/settings/sandbox")
async def get_sandbox_settings():
    return {
        "default_image": "nikolaik/python-nodejs",
        "available_sizes": [
            {"name": "small", "cpu": 1, "memory_gb": 2},
            {"name": "medium", "cpu": 2, "memory_gb": 4},
            {"name": "large", "cpu": 4, "memory_gb": 8},
        ],
        "network_mode": "allow_all",
    }
```

**Effort:** 2-3 days

---

### 5.5 No Cross-Session Context for Chat Agent

**Files involved:** None

**What:** When the user returns after a run, the agent has no memory of what happened. Must re-explain context.

**2026 context — Microsoft FileMemoryProvider (BUILD 2026):**
MAF provides "session-scoped file-based memory so the agent can persist notes/learnings across turns; stored in `agent-file-memory/{session}/`."

**Fix: Inject session summary into chat context** (2-3 days):
```python
async def get_session_context(session_id: str) -> str:
    session = await db.fetchrow(
        "SELECT goal, status, duration_sec, model FROM sessions WHERE session_id=$1",
        session_id
    )
    tasks = await db.fetch(
        "SELECT title, status FROM kanban_tasks WHERE session_id=$1",
        session_id
    )
    return f"""Session: {session['status']}
Goal: {session['goal'][:200]}
Duration: {session['duration_sec']:.0f}s
Tasks completed: {sum(1 for t in tasks if t['status']=='done')}/{len(tasks)}
"""
```

**Effort:** 2-3 days

---

## 6. Tool & Skills System

### 6.1 Tool Registration — Codegraph Tools Have No Tests

**Files involved:** `backend/harness/tools/` (codegraph tools)

**What:** The 79-tool catalog includes codegraph tools but several have no test coverage:

```
codegraph_search    — ⚠️ basic tests exist
codegraph_node      — ⚠️ basic tests exist
codegraph_callees   — ✅ registered, no tests
codegraph_callers   — ✅ registered, no tests
codegraph_explore   — ❌ no tests
codegraph_impact    — ❌ no tests
codegraph_files     — ❌ no tests
codegraph_status    — ❌ no tests
```

**2026 context — CodeGraph ecosystem (codegraph-ai, June 2026):**
CodeGraph now provides 45 MCP tools covering 37 languages via tree-sitter, with 3,000+ GitHub stars. Semantic code graph approach is standardizing fast. TestAI's codegraph tools need test coverage to stay reliable.

**Fix: Add test coverage for all 8 codegraph tools** (2-3 days)

**Effort:** 2-3 days

---

### 6.2 No Persistent Per-Tool Health Tracking

**Files involved:** `backend/harness/core/events.py`, `src/components/activity/ObservabilityPanels.tsx`

**What:** Per-tool success rate is computed from live SSE events only. No persistent health table, no latency history, no trend detection.

**2026 context — Microsoft Agent Framework (BUILD 2026):**
MAF's `OpenTelemetryAgent` auto-instruments every tool call with OTel spans, providing persistent metrics queryable historically.

**Fix: Add tool_health table** (3-5 days):
```sql
CREATE TABLE tool_health (
    tool_name TEXT PRIMARY KEY,
    total_calls INTEGER DEFAULT 0,
    error_calls INTEGER DEFAULT 0,
    avg_duration_ms REAL DEFAULT 0,
    p50_duration_ms REAL DEFAULT 0,
    p95_duration_ms REAL DEFAULT 0,
    last_called_at TIMESTAMP,
    last_error_at TIMESTAMP,
    last_error_message TEXT
);
```

**Effort:** 3-5 days

---

### 6.3 ~~Error Classifier — Incomplete Categories (F3)~~ ✅ IMPLEMENTED

**Status:** `ErrorClassifier` is fully implemented at `backend/harness/tools/error_classifier.py` (66 lines) with 10 categories (rate_limit, auth, timeout, context_length, server_error, quota, stream_error, invalid_request, model_overload, circuit_open), wired into `agent.py:891` (LLM error → classified ErrorEvent) and `subagent.py:594-599` (subagent retry decisions). Retryable/non-retryable classification drives fallback logic.

---

### 6.4 No Skill Versioning or Testing

**Files involved:** `docs/agent-skills/skills/` (skill definitions)

**What:** Skills are plain `SKILL.md` files with no versioning, testing, A/B testing, rollback, or usage metrics.

**2026 context — GitHub Copilot Plugins & Marketplace (BUILD 2026):**
Skills are evolving from local files to distributed, versioned, marketplace-hosted packages. Copilot's plugin marketplace hosts installable packages that bundle custom agents, skills, hooks, MCP servers, and LSP integrations into single distributable units.

**Fix: Add skill metadata and validation** (2-3 days):
```yaml
# SKILL.md frontmatter:
---
name: test-driven-development
version: 1.2.0
min_tool_catalog_version: 2
changelog:
  - version: 1.2.0
    changes: ["Updated test patterns for pytest 8.x"]
---
```

**Effort:** 2-3 days

---

### 6.5 ErrorEvent Missing Structured Diagnostics (F24)

**Files involved:** `backend/harness/core/events.py:199`

**What:** `ErrorEvent` lacks structured diagnostic fields. Dashboard shows count only — no provider, model, tool, or traceback context.

**Fix: Expand ErrorEvent** (1-2 days):
```python
@dataclass
class ErrorEvent:
    message: str
    recoverable: bool
    category: str = ""
    session_id: str = ""
    agent_id: str = ""
    # NEW:
    provider: str = ""
    model: str = ""
    tool_name: str = ""
    request_id: str = ""
    status_code: int = 0
    traceback: str = ""
    subagent_id: str = ""
```

**Effort:** 1-2 days

---

## 7. Kanban & Project Management

### 7.1 Kanban Column Default Mismatch (F10)

**Files involved:** DB schema, `backend/api/routers/kanban.py`

**What:** Two different default column lists. DB default: 6 cols, no `triage`. API default: 7 cols with `triage`. DB default is dead code — every board is created with explicit columns from the API. If someone creates a board without `columns`, they get 6 cols and the UI breaks.

**Fix: Align defaults** (<1 day):
```sql
ALTER TABLE kanban_boards 
ALTER COLUMN columns SET DEFAULT 
'{"triage","backlog","ready","in_progress","review","done","flaky_heat"}';
```

**Effort:** <1 day

---

### 7.2 Goal Decomposition Hallucination (F6)

**Files involved:** `backend/harness/tools/orchestrator_tool.py:1-56`

**What:** LLM `_llm_decompose` produces tasks unrelated to the prompt. Observed: "PR 37724 cache_version" → tasks about "fix unhashable type: slice". System prompt fragments leak into task titles.

**Fix: Entity sanity check** (1 day):
```python
def _validate_decomposition(prompt: str, tasks: list[dict]) -> list[dict]:
    entities = set()
    entities.update(re.findall(r'PR\s*#?(\d+)', prompt, re.I))
    entities.update(re.findall(r"'([^']+)'", prompt))
    entities.update(re.findall(r'\b([A-Z]\w+(?:::?\w+)*)\b', prompt))
    
    valid = [t for t in tasks 
             if any(e.lower() in f"{t.get('title','')} {t.get('description','')}".lower()
                    for e in entities if len(e) > 2)]
    return valid or tasks
```

**Effort:** 1 day

---

### 7.3 System Prompt Leaks Into Task Titles (F19)

**Files involved:** `backend/harness/tools/orchestrator_tool.py`

**What:** LLM echoes system prompt in task titles before JSON. JSON parser drops prefix, but system prompt text enters the title field.

**Fix: Strip system prompt before JSON parse** (<1 day):
```python
def _strip_system_prompt(text: str, system_prompt: str) -> str:
    for frag in re.findall(r'"[^"]{20,}"', system_prompt):
        text = text.replace(frag, "")
    text = re.sub(r'^You are a \w+\.\s*', '', text)
    return text.strip()
```

**Effort:** <1 day

---

### 7.4 No Task Dependency Tracking

**Files involved:** `backend/api/routers/kanban.py`

**What:** Tasks can't express dependencies. No critical path, no blocker detection, no circular dependency detection.

**2026 context — Modern Agent Harness Blueprint (March 2026):**
Blueprint's Task entity has `dependencies`, `blockers`, and `artifact_refs` as first-class fields.

**Fix: Add dependency fields** (2-3 days):
```python
@dataclass
class KanbanTask:
    id: str
    title: str
    status: str = "backlog"
    priority: str = "medium"  # critical | high | medium | low
    dependencies: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    assigned_to: str = ""
```

**Effort:** 2-3 days

---

### 7.5 No Task Time Estimation

**Files involved:** `backend/api/routers/kanban.py`

**What:** No estimated effort, actual time, or deadlines. Can't answer "how much work is left" or detect "this task is taking too long."

**Fix: Add time tracking fields** (1-2 days):
```python
@dataclass
class KanbanTask:
    estimated_minutes: int = 0
    actual_minutes: int = 0
    deadline: str = ""
    started_at: float = 0
    completed_at: float = 0
```

**Effort:** 1-2 days

---

## 8. Budget, Cost & Rate Limiting

### 8.1 Circuit Breaker Threshold Too Sensitive (F13)

**Files involved:** `backend/harness/tools/circuit_breaker.py`

**What:** The circuit breaker opens at 50% failure rate over 60s with min 5 requests. With a 79-tool catalog, a single burst of 5 errors trips the breaker for 30s, starving all subsequent subagents.

**Current:**
```python
failure_threshold: float = 0.5
min_requests: int = 5
recovery_timeout: int = 30
```

**Impact (F13 finding):** First subagent hit 400 error → breaker opened at `rate=1.00` → every subsequent subagent failed with "circuit_open" — 10 subagents dead before any could retry.

**2026 context — Ranjan Kumar Harness Engineering:**
Circuit breaker should use configurable thresholds per-role, with `min_requests` floor to prevent opening on sparse data, and HALF_OPEN probe traffic at 10% rate.

**Fix: Per-role circuit breaker config** (2-3 days):
```python
CIRCUIT_BREAKER_CONFIG = {
    "coordinator": {"failure_threshold": 0.3, "min_requests": 20, "recovery_timeout": 120},
    "explore": {"failure_threshold": 0.5, "min_requests": 10, "recovery_timeout": 60},
    "fix": {"failure_threshold": 0.7, "min_requests": 5, "recovery_timeout": 30},
    "leaf": {"failure_threshold": 0.7, "min_requests": 3, "recovery_timeout": 30},
}
```

**Effort:** 2-3 days

---

### 8.2 No Per-Tool Cost Tracking

**Files involved:** `backend/harness/budget_tracker.py`

**What:** Budget tracker tracks run-level totals only. Cannot answer "which tool is most expensive?"

**Fix: Add per-tool cost aggregation** (2-3 days):
```sql
SELECT tool_name, COUNT(*) AS calls,
       SUM(prompt_tokens + completion_tokens) * 0.000002 AS cost_usd
FROM tool_execution_events WHERE session_id = $1
GROUP BY tool_name ORDER BY cost_usd DESC;
```

**Effort:** 2-3 days

---

### 8.3 Spawn Rate Limiter Not Configurable Per-Role

**Files involved:** `backend/harness/tools/subagent.py`

**What:** Rate limits are hardcoded env vars. Not configurable per-role or per-run.

**Fix: Per-role rate limits** (1-2 days):
```python
ROLE_RATE_LIMITS = {
    "coordinator": {"limit": 20, "window": 60, "cooldown": 30},
    "explore": {"limit": 10, "window": 30, "cooldown": 60},
    "fix": {"limit": 5, "window": 30, "cooldown": 120},
}
```

**Effort:** 1-2 days

---

### 8.4 No Per-Subagent Budget Cap

**Files involved:** `backend/harness/budget_tracker.py`

**What:** Run-level budget only. A runaway subagent can consume the entire run budget.

**Fix: Per-subagent budget caps** (2-3 days):
```python
SUBAGENT_BUDGET = {
    "explore": {"max_cost_usd": 0.50, "max_tool_calls": 20},
    "fix": {"max_cost_usd": 2.00, "max_tool_calls": 50},
    "review": {"max_cost_usd": 1.00, "max_tool_calls": 30},
}
```

**Effort:** 2-3 days

---

## 9. Data Persistence, Multi-Repo & Lifecycle

### 9.1 No Cross-Repo Volume Sharing

**Files involved:** `backend/harness/sandbox_manager.py`

**What:** Each session creates a separate Docker volume. Two sessions on the same repo rebuild KG + deps from scratch. No mechanism to share volumes across sessions keyed by repo.

**Current:** Volume name based on `session_id` only — no repo awareness.

**Impact:** KG rebuilt per run, deps reinstalled, build caches lost. 5-10 min wasted per run.

**Competitor reference — Greptile TREX:** "Reusable base images and per-repository snapshots. A repository can be cloned once, captured, and resumed."

**Fix: Repo-keyed volume sharing** (2-3 days):
```python
def _repo_volume_name(self, repo_url: str) -> str:
    repo_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:12]
    return f"testai-repo-{repo_hash}"

async def get_or_create(self, session_id, *, repo_url=None, ...):
    volume_key = self._repo_volume_name(repo_url) if repo_url else session_id
    return await self._create_env(session_id, volume_key=volume_key)
```

**Effort:** 2-3 days

---

### 9.2 No Sandbox Idle Reaper

**Files involved:** `backend/harness/sandbox_manager.py`

**What:** Sandbox containers persist indefinitely. No idle timeout, no max-age cleanup, no reaper.

**Impact:** Container leak, disk exhaustion, port conflicts, cost waste.

**Fix: Background reaper task** (2-3 days):
```python
class SandboxReaper:
    MAX_IDLE_SECONDS = 3600
    MAX_AGE_SECONDS = 86400
    
    async def reap(self):
        while True:
            await asyncio.sleep(300)
            for rec in self._registry.list_all():
                idle = time.time() - rec.last_activity
                age = time.time() - rec.created_at
                if idle > self.MAX_IDLE_SECONDS or age > self.MAX_AGE_SECONDS:
                    await self._sandbox_manager.destroy_env(rec.session_id)
```

**Effort:** 2-3 days

---

### 9.3 No Multi-Repo Coordination

**Files involved:** `backend/harness/orchestrator.py` (run_multi)

**What:** `run_multi()` exists but is dead code. No actual cross-repo workflow — no dependency resolution, shared KG, or coordinated PRs across repos.

**2026 context — GitHub Copilot (June 2026):**
"Individual developers can now fan out refactors across repos, automate releases, and integrate cloud agent tasks into personal pipelines."

**Fix: Implement multi-repo JobSpec** (5-7 days):
```python
class JobSpec:
    prompt: str
    repo_url: str
    context_repos: list[dict] = []  # Related repos
    # [{"url": "https://github.com/org/lib", "scope": "dependency"}]
```

**Effort:** 5-7 days

---

### 9.4 No User-Configurable Artifact Lifecycle

**Files involved:** `backend/harness/services/artifact_store.py`

**What:** Artifact TTLs are hardcoded (tests=permanent, trajectories=30d, transcripts=7d). No UI to configure.

**Fix: Artifact settings API** (2-3 days):
```python
@router.get("/api/settings/artifacts")
async def get_artifact_settings():
    return {
        "test_files_ttl_days": 0,
        "trajectories_ttl_days": 30,
        "llm_transcripts_ttl_days": 7,
        "screenshots_ttl_days": 90,
        "max_artifacts_per_run": 1000,
        "max_total_storage_gb": 10,
    }
```

**Effort:** 2-3 days

---

## 10. Testing & CI/CD Integration

### 10.1 No Orchestrator Integration Tests

**Files involved:** `backend/harness/orchestrator.py`

**What:** `run_multi` has 0 tests and 1 caller. `run_single` has no direct tests. `run_job_spec` has no dedicated tests. The only coverage comes from manual e2e runs.

**Fix: Add orchestrator integration tests** (3-5 days):
```python
@pytest.mark.asyncio
async def test_run_job_spec_basic():
    engine = OrchestratorEngine.create_default()
    spec = JobSpec(prompt="List repo files", repo_url="https://github.com/example/test", tier=1)
    result = await engine.run_job_spec(spec)
    assert result["success"] is True
    session = await db.fetchrow("SELECT status FROM sessions WHERE session_id=$1", result["session_id"])
    assert session["status"] == "completed"
```

**Effort:** 3-5 days

---

### 10.2 No CI/CD E2E Pipeline Test

**Files involved:** `.github/workflows/`

**What:** CI runs unit tests only. No Docker-based e2e test that verifies the full flow: submit job → clone → explore → fix → verify → report.

**Fix: Add e2e workflow** (3-5 days):
```yaml
# .github/workflows/e2e.yml
jobs:
  e2e:
    steps:
      - run: docker compose up -d
      - run: curl -X POST /api/jobs -d '{"prompt":"test","repo_url":"...","tier":1}'
      - run: ./scripts/verify-kanban.sh && ./scripts/verify-subagents.sh
```

**Effort:** 3-5 days

---

### 10.3 No Flaky Test Detection

**Files involved:** None

**What:** No mechanism to detect, flag, auto-retry, or quarantine flaky tests across runs.

**Competitor reference — TestSprite:** Classifies failures (real bug vs fragility vs environment), auto-heals flaky tests.
**Competitor reference — Mabl:** Built-in flaky detection with auto-retry and quarantine.

**Fix: Flaky test detector** (3-5 days):
```python
class FlakyTestDetector:
    FLAKY_THRESHOLD = 0.3
    
    async def analyze(self, test_name: str) -> dict:
        history = await db.fetch(
            "SELECT result FROM test_results WHERE test_name=$1 ORDER BY created_at DESC LIMIT 20",
            test_name
        )
        if len(history) < 3:
            return {"flaky": False, "reason": "insufficient_data"}
        pass_rate = sum(1 for r in history if r["result"] == "pass") / len(history)
        return {"flaky": pass_rate < self.FLAKY_THRESHOLD, "pass_rate": pass_rate}
```

**Effort:** 3-5 days

---

### 10.4 No Test Result → Artifact Linking

**Files involved:** `backend/harness/services/artifact_store.py`

**What:** Test results not linked to the test file, commit, or subagent that produced them.

**Fix: Add test result metadata** (1-2 days):
```python
@dataclass
class TestResult:
    test_name: str
    result: str
    file_path: str
    commit_sha: str
    subagent_id: str
    session_id: str
    error_message: str = ""
```

**Effort:** 1-2 days

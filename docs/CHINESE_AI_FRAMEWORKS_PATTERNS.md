# Chinese AI Frameworks — Adoptable Patterns

> **Date:** 2026-06-17
> **Frameworks:** Kimi Code (Moonshot AI), GLM-4.5 (Z.AI/Zhipu), MiniMax M2.7
> **Goal:** Features and patterns we can adopt into TestAI

---

## 1. Kimi Code (Moonshot AI)

### Architecture
- **Single-binary distribution** — No Node.js setup, one command install
- **Subagent system** — Built-in `coder`, `explore`, `plan` subagents
- **Isolated contexts** — Each subagent has its own context history
- **Persistent instances** — Subagents can be resumed across calls
- **ACP protocol** — Agent Client Protocol for IDE integration (Zed, JetBrains)

### Key Features to Adopt

#### 1.1 Three Built-in Subagent Types
```python
# Kimi Code has 3 focused subagent types:
KIMI_SUBAGENTS = {
    "coder": {
        "description": "General software engineering",
        "tools": ["read", "write", "edit", "bash", "search"],
        "context": "isolated",  # Clean context window
    },
    "explore": {
        "description": "Fast read-only codebase exploration",
        "tools": ["read", "glob", "grep", "search"],
        "context": "isolated",
    },
    "plan": {
        "description": "Implementation planning and architecture design",
        "tools": ["read", "glob", "grep", "search"],
        "context": "isolated",
    },
}

# Our equivalent: coordinator, bug-fixer, test-writer, etc.
# But Kimi's are simpler and more focused
```

#### 1.2 Permission Inheritance
```python
# Kimi: "always allow" rules inherit to subagents
# No re-approval needed for same tool calls
class PermissionInheritance:
    def __init__(self):
        self.always_allow = set()  # User-accepted permissions
    
    def check_subagent_permission(self, tool_name, subagent_id):
        """Subagent inherits parent's always-allow rules."""
        if tool_name in self.always_allow:
            return True  # Auto-approve
        return self.ask_permission(tool_name, subagent_id)
```

#### 1.3 Multi-Step Tool Calling (Native to K2.7)
```python
# K2.7 does 3-5x fewer API calls than Aider
# Because it can chain multiple file operations in one turn
# Aider: read file → model call → write file → model call → ...
# K2.7: read + write + edit in single model response

# Our fix: The dict vs SimpleNamespace issue was blocking this
# Now mimo-v2.5 produces tool_calls correctly
```

#### 1.4 MCP Configuration via Chat
```python
# Kimi: /mcp-config command to add/edit MCP servers conversationally
# No hand-editing JSON needed
KIMI_MCP_CONFIG = {
    "command": "/mcp-config",
    "description": "Add, edit, authenticate MCP servers via chat",
    "trust_levels": ["verified", "unverified", "custom"],
}
```

### Priority: HIGH — Adopt 3 subagent types + permission inheritance

---

## 2. GLM-4.5 (Z.AI/Zhipu)

### Architecture
- **355B parameters, 32B active** — MoE architecture
- **Hybrid reasoning** — Thinking + direct response modes
- **Native function calling** — Optimized for tool use
- **128K context** — Long-horizon agent tasks

### Key Features to Adopt

#### 2.1 CLAWS Framework (Continuous Long-horizon Agentic Workflow)
```python
# GLM's CLAWS: experiment → analyze → optimize loop
# Model runs complete loops autonomously, not step-by-step

class CLAWSLoop:
    async def run_loop(self, objective):
        """Continuous experiment → analyze → optimize."""
        while not self.satisfied(objective):
            # Plan
            plan = await self.model.plan(objective, current_state)
            
            # Execute
            results = await self.execute_plan(plan)
            
            # Analyze
            analysis = await self.analyze_results(results)
            
            # Optimize
            objective = self.optimize_objective(objective, analysis)
        
        return self.final_output()
```

#### 2.2 Thinking + Direct Response Modes
```python
# GLM supports both modes:
# 1. Thinking mode: Chain-of-thought before answer
# 2. Direct mode: Immediate response

class ThinkingModeManager:
    def get_mode_for_task(self, task_type):
        """Select thinking mode based on task complexity."""
        if task_type in ("complex_reasoning", "multi_step"):
            return "thinking"  # CoT before answer
        elif task_type in ("simple_qa", "tool_call"):
            return "direct"  # Immediate response
        else:
            return "auto"  # Model decides
```

#### 2.3 Native Function Calling Optimization
```python
# GLM-4.5 optimized for tool invocation
# Better tool_call reliability than DeepSeek V4

GLM_TOOL_CONFIG = {
    "supports_tool_choice": True,  # Unlike DeepSeek V4
    "requires_reasoning_roundtrip": False,  # No echo needed
    "preferred_structured_method": "function_calling",
}
```

### Priority: MEDIUM — Adopt CLAWS loop pattern

---

## 3. MiniMax M2.7

### Architecture
- **OpenAI-compatible API** — Same SDK, different base_url
- **Temperature requirement** — Must be > 0 (unusual)
- **Sandbox integration** — Jupyter + Node.js execution

### Key Features to Adopt

#### 3.1 Temperature Floor
```python
# MiniMax requires temperature > 0
# We should add validation

class TemperatureValidator:
    MIN_TEMPERATURES = {
        "minimax-m2.7": 0.01,
        "minimax-m2.5": 0.01,
        "minimax-m3": 0.01,
        "default": 0.0,
    }
    
    def validate(self, model: str, temperature: float) -> float:
        """Ensure temperature meets model requirements."""
        min_temp = self.MIN_TEMPERATURES.get(model, 0.0)
        return max(temperature, min_temp)
```

#### 3.2 Sandbox + LLM Integration
```python
# MiniMax pattern: LLM generates code → Sandbox executes
# Clean separation of concerns

class MiniMaxPattern:
    def __init__(self, llm, sandbox):
        self.llm = llm
        self.sandbox = sandbox
    
    async def execute_code(self, prompt):
        """LLM generates code, sandbox executes."""
        response = await self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "run_code",
                    "parameters": {"code": str, "lang": str},
                },
            }],
        )
        
        if response.tool_calls:
            args = json.loads(response.tool_calls[0].function.arguments)
            result = await self.sandbox.execute(**args)
            return result
```

#### 3.3 OpenAI-Compatible Pattern
```python
# MiniMax uses same SDK as OpenAI
# Just different base_url and API key

MINIMAX_CONFIG = {
    "base_url": "https://api.minimax.io/v1",
    "api_key": "your_minimax_api_key",
    "model": "MiniMax-M2.7",
    "temperature": 0.01,  # Required > 0
}
```

### Priority: LOW — Adopt temperature validation

---

## 4. Common Patterns Across All Three

### 4.1 Subagent Isolation
All three frameworks isolate subagent contexts:
- **Kimi:** `subagents/<agent_id>/` directory per subagent
- **GLM:** Separate context windows for each agent
- **MiniMax:** Sandbox isolation per execution

**Our adoption:** We already have this via Docker volumes per session. ✅

### 4.2 Permission Inheritance
All three inherit permissions from parent to subagent:
- **Kimi:** "always allow" rules auto-apply to subagents
- **GLM:** Permission context flows through delegation
- **MiniMax:** Sandbox permissions inherited

**Our adoption:** Need to implement permission inheritance in our PermissionManager.

### 4.3 MCP Integration
All three support Model Context Protocol:
- **Kimi:** Conversational MCP config via `/mcp-config`
- **GLM:** Native MCP support in agent framework
- **MiniMax:** MCP tools available via OpenAI-compatible API

**Our adoption:** We have MCP support but need better configuration UX.

### 4.4 Thinking Mode Control
All three control thinking mode:
- **Kimi:** K2.5/K2.6/K2.7 thinking modes
- **GLM:** Hybrid thinking + direct response
- **MiniMax:** Temperature-based control

**Our adoption:** We fixed this with `reasoning_effort` config. ✅

---

## Summary: Priority Matrix from Chinese Frameworks

| Priority | Pattern | Source | Effort | Impact |
|----------|---------|--------|--------|--------|
| HIGH | 3 focused subagent types (coder/explore/plan) | Kimi | Low | Simpler agent model |
| HIGH | Permission inheritance to subagents | Kimi | Medium | Better UX |
| HIGH | Multi-step tool calling (native) | Kimi K2.7 | Already fixed | 3-5x fewer API calls |
| MEDIUM | CLAWS continuous loop pattern | GLM | Medium | Better long-horizon tasks |
| MEDIUM | Thinking + direct response modes | GLM | Low | Flexibility |
| LOW | Temperature floor validation | MiniMax | Low | Prevent API errors |
| LOW | Conversational MCP config | Kimi | Medium | Better UX |

---

*Document created: 2026-06-17*

"""Runtime Recovery — agent-level retry, replan, degrade strategies.

Recovery strategies wrap a single agent turn. When a tool call fails
the strategy decides: retry with backoff, try an alternative approach,
gracefully degrade (mark and continue), or escalate.

Role YAML config:
  recovery:
    max_retries: 2
    retry_delay: 1.0
    replan_on: ["tool_error", "timeout"]
    degrade_on: ["validation_warning"]
    escalate_on: ["permission_denied", "budget_exceeded"]
"""

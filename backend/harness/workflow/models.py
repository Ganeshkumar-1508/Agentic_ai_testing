"""Workflow models — reusable step definitions for multi-step agent workflows.

A WorkflowDefinition wraps a list of WorkflowSteps that the WorkflowExecutor
executes by dispatching to existing harness primitives (delegate_task, question,
kanban, etc.). The same model is used by both the form-based BlueprintPanel
and the visual ReactFlow canvas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


StepType = Literal["agent", "human_input", "router", "sub_workflow"]
StepMode = Literal["sequential", "parallel", "conditional"]
ExecutionStatus = Literal["running", "completed", "failed", "cancelled"]


@dataclass
class StepExecutionRecord:
    """A single step's execution outcome within a workflow run."""

    step_id: str
    label: str
    type: str
    status: ExecutionStatus | str
    started_at: str
    duration_sec: float
    output: str = ""
    error: str = ""


@dataclass
class WorkflowExecutionRecord:
    """A single run of a workflow definition."""

    id: str
    workflow_key: str
    status: ExecutionStatus
    started_at: str
    completed_at: str = ""
    duration_sec: float = 0.0
    steps: list[StepExecutionRecord] = field(default_factory=list)
    error: str = ""
    triggered_by: str = "manual"
    retry_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_key": self.workflow_key,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_sec": self.duration_sec,
            "steps": [
                {"step_id": s.step_id, "label": s.label, "type": s.type,
                 "status": s.status, "started_at": s.started_at,
                 "duration_sec": s.duration_sec, "output": s.output[:200],
                 "error": s.error[:200]}
                for s in self.steps
            ],
            "error": self.error,
            "triggered_by": self.triggered_by,
            "retry_of": self.retry_of,
        }


@dataclass
class BranchRule:
    """A single conditional branch in a router step."""

    label: str
    condition: str
    target_step: str


@dataclass
class WorkflowStep:
    """A single step in a multi-step agent workflow.

    dispatches to an existing harness primitive at execution time:
      - agent       → delegate_task (subagent)
      - human_input → question tool (HITL pause)
      - router      → branch evaluation (conditional routing)
      - sub_workflow → recursive WorkflowExecutor
    """

    id: str
    label: str
    type: StepType
    prompt: str
    mode: StepMode = "sequential"
    depends_on: list[str] = field(default_factory=list)
    config: dict = field(default_factory=lambda: {
        "model": None,
        "toolsets": ("read",),
        "timeout_sec": 300,
        "role": "leaf",
    })
    branch_rules: list[BranchRule] = field(default_factory=list)
    children: list[WorkflowStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "prompt": self.prompt,
            "mode": self.mode,
            "depends_on": list(self.depends_on),
            "config": dict(self.config),
            "branch_rules": [{"label": r.label, "condition": r.condition, "target_step": r.target_step} for r in self.branch_rules],
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            id=data["id"],
            label=data.get("label", data["id"]),
            type=data["type"],
            prompt=data.get("prompt", ""),
            mode=data.get("mode", "sequential"),
            depends_on=list(data.get("depends_on", [])),
            config=dict(data.get("config", {})),
            branch_rules=[BranchRule(**r) for r in data.get("branch_rules", [])],
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )


@dataclass
class WorkflowDefinition:
    """A named, versioned workflow composed of steps.

    Stored as a blueprint extension in the existing cron_jobs / blueprints
    system. Can be triggered on-demand or scheduled.
    """

    key: str
    title: str
    description: str
    category: str = "Workflow"
    steps: list[WorkflowStep] = field(default_factory=list)
    tags: tuple = ()
    schedule_template: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "steps": [s.to_dict() for s in self.steps],
            "tags": list(self.tags),
            "schedule_template": self.schedule_template,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowDefinition:
        return cls(
            key=data["key"],
            title=data.get("title", data["key"]),
            description=data.get("description", ""),
            category=data.get("category", "Workflow"),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            tags=tuple(data.get("tags", [])),
            schedule_template=data.get("schedule_template", ""),
        )

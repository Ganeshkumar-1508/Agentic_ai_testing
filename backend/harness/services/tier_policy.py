"""TierPolicy &mdash; orchestrator's tier-aware goal + proposal logic.

Wire of C03 (orchestrator decomposition). The original
:class:`harness.orchestrator.OrchestratorEngine` carried the
tier-1/2/3 semantics in five static + instance methods. This
module pulls them out so the orchestrator becomes thin assembly
and the tier rules live in one place.

Per :mod:`CONTEXT.md` glossary:
- Tier 1 (autonomous) &mdash; full toolset, PR auto-opens on success
- Tier 2 (supervised) &mdash; full toolset, but stops before
  ``commit_and_open_pr`` and posts to a review queue
- Tier 3 (human-authored) &mdash; the orchestrator does NOT run
  the agent. It creates a kanban board with the spec's prompt
  and waits for human approval

The three concerns are:
1. :func:`build_goal` &mdash; render the coordinator's goal string
   from a JobSpec + the role file at
   ``.testai/prompts/agents/coordinator.txt``
2. :func:`proposal_id` &mdash; the tier-2 path: write a
   ``Proposal`` row to the durable store so the review queue
   knows about it
3. :func:`human_authored_proposal` &mdash; the tier-3 path:
   create a kanban board with a single "awaiting human review" task

The orchestrator's methods (``_build_tier_aware_goal``,
``_vars_for_job_spec``, ``_fallback_tier_aware_goal``,
``_create_tier2_proposal``, ``_run_human_authored_proposal``)
become thin delegates that call this module. New code should
call :class:`TierPolicy` directly; the orchestrator's static
methods are kept for backward compat with anything that
imports them.
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class TierPolicy:
    """Tier-aware goal + proposal logic.

    The methods on this class are :func:`staticmethod` or
    :func:`classmethod` because tier rules are pure functions
    of a JobSpec &mdash; no instance state, no per-Run
    state. The orchestrator's role is to call these and pass
    the result downstream; it doesn't own tier policy.
    """

    #: The default capability set the coordinator is allowed to
    #: use. Used by the FORBIDDEN block in the goal string. The
    #: orchestrator always adds "delegate_task" for tier-2+
    #: so a coordinator can fan out; the FORBIDDEN list in the
    #: goal string is the per-spec refinement.
    DEFAULT_FORBIDDEN: ClassVar[tuple[str, ...]] = (
        "open_pr",
        "write_test_files",
        "edit_existing_tests",
        "run_tests",
    )

    # ------------------------------------------------------------------
    # Tier-agnostic: build the goal string the coordinator sees.
    # ------------------------------------------------------------------

    @staticmethod
    def build_goal(spec: Any, proposal_id: str | None = None) -> str:
        """Render the coordinator's goal string from the role file.

        The role body lives at
        ``.testai/prompts/agents/coordinator.txt`` (loaded via
        :func:`harness.prompt_builder.load_agent_prompt`). The
        dynamic parts (capability list, tier-specific instructions)
        are computed by :func:`vars_for_spec` and substituted into
        the ``{{header}}`` and ``{{tier_block}}`` placeholders.

        If the role file is missing (fresh install, deleted by
        mistake) we fall back to the inline f-string in
        :func:`fallback_goal` so the system never breaks at
        startup. The fallback is the pre-C1.1 behaviour; the
        file-based path is the v1.

        ``tier=1`` is the default; no tier-specific block.
        ``tier=2`` adds the explicit "queue for review"
        instructions and (when the ProposalStore is wired) the
        ``proposal_id`` reference. Capabilities not in the spec
        are listed in the FORBIDDEN block.
        """
        from harness.prompt_builder import render_prompt
        from harness.agent_discovery import get_agent

        agent = get_agent("orchestrator")
        body = agent.prompt if agent else ""
        if not body:
            return TierPolicy.fallback_goal(spec, proposal_id)

        return render_prompt(body, TierPolicy.vars_for_spec(spec, proposal_id))

    @staticmethod
    def vars_for_spec(spec: Any, proposal_id: str | None = None) -> dict[str, str]:
        """Compute the substitution vars for the coordinator role body.

        Returns a dict with two keys:
        - ``header``: the spec's prompt / repo / branch / tier /
          capabilities / forbidden block. Always present.
        - ``tier_block``: tier-specific instructions (empty for
          tier 1; the tier-2 supervised block otherwise).
        """
        capabilities = spec.capabilities or []
        forbidden = [
            c for c in TierPolicy.DEFAULT_FORBIDDEN
            if c not in capabilities
        ]
        cap_lines = "\n".join(f"  - {c}" for c in capabilities)
        if forbidden:
            forbidden_block = (
                "\n\nFORBIDDEN (do NOT do these):\n"
                + "\n".join(f"  - {c}" for c in forbidden)
            )
        else:
            forbidden_block = "\n(no additional restrictions)"

        header = (
            f"PROMPT: {spec.prompt}\n"
            f"REPO: {spec.repo_url or '(not specified)'}\n"
            f"BRANCH: {spec.branch or 'main'}\n"
            f"TIER: {spec.tier}\n"
            f"\nCAPABILITIES (you MAY do these):\n"
            f"{cap_lines}"
            f"{forbidden_block}"
        )

        tier_block = ""
        if spec.tier == 2:
            proposal_ref = ""
            if proposal_id:
                proposal_ref = (
                    f"\nThis work is tracked as proposal `{proposal_id}` "
                    "in the review queue. Reference this id in your "
                    "kanban post so the reviewer can find the proposal."
                )
            tier_block = (
                "\nTIER 2 \u2014 SUPERVISED:\n"
                "After you have committed the fix locally and tests pass, "
                "do NOT call commit_and_open_pr. Instead, post the diff "
                "and a summary of the change as a kanban task and stop. "
                "A human reviewer will approve the kanban task, at which "
                "point the orchestrator's CI step will open the PR."
                f"{proposal_ref}"
            )

        return {"header": header, "tier_block": tier_block}

    @staticmethod
    def fallback_goal(spec: Any, proposal_id: str | None = None) -> str:
        """Pre-C1.1 f-string fallback.

        Used only when ``.testai/prompts/agents/coordinator.txt``
        is missing. Kept here so a fresh install without the role
        file still functions. The file-based path (via
        :func:`build_goal`) is the source of truth going forward.
        """
        capabilities = spec.capabilities or []
        forbidden = []
        if "open_pr" not in capabilities:
            forbidden.append("open_pr")
        if "write_test_files" not in capabilities:
            forbidden.append("write_test_files")
        if "edit_existing_tests" not in capabilities:
            forbidden.append("edit_existing_tests")
        if "run_tests" not in capabilities:
            forbidden.append("run_tests")

        tier_2_block = ""
        if spec.tier == 2:
            proposal_ref = (
                f"\nThis work is tracked as proposal `{proposal_id}` "
                f"in the review queue. Reference this id in your "
                f"kanban post so the reviewer can find the proposal.\n"
                if proposal_id else ""
            )
            tier_2_block = (
                "\nTIER 2 \u2014 SUPERVISED:\n"
                "After you have committed the fix locally and tests pass, "
                "do NOT call commit_and_open_pr. Instead, post the diff "
                "and a summary of the change as a kanban task and stop. "
                "A human reviewer will approve the kanban task, at which "
                "point the orchestrator's CI step will open the PR."
                f"{proposal_ref}\n"
            )

        cap_block = (
            f"\nCAPABILITIES (you MAY do these):\n"
            + "\n".join(f"  - {c}" for c in capabilities)
            + (f"\n\nFORBIDDEN (do NOT do these):\n"
               + "\n".join(f"  - {c}" for c in forbidden)
               if forbidden else "\n(no additional restrictions)\n")
        )

        return (
            f"You are the coordinator for this TestAI job. The job was "
            f"submitted by the chat Role with the following spec:\n\n"
            f"PROMPT: {spec.prompt}\n"
            f"REPO: {spec.repo_url or '(not specified)'}\n"
            f"BRANCH: {spec.branch or 'main'}\n"
            f"TIER: {spec.tier}\n"
            f"{cap_block}"
            f"{tier_2_block}\n"
            f"WORKFLOW:\n"
            f"1. Plan the work via orquestrate(goal=...). The LLM "
            f"decomposes the prompt into 2-6 kanban subtasks.\n"
            f"2. Monitor with orquestrate_monitor and re-plan if stalled.\n"
            f"3. Use delegate_task for parallel work; use bash to run "
            f"commands; use memory to save lessons learned.\n"
            f"4. Run tests after each change. Triage failures via the "
            f"knowledge graph.\n"
            f"5. After tests pass, follow the TIER-specific instructions "
            f"above for opening a PR (or queuing for review).\n"
            f"6. Report what you accomplished.\n"
        )

    # ------------------------------------------------------------------
    # Tier-specific: side-effecting paths.
    # ------------------------------------------------------------------

    @staticmethod
    async def proposal_id(spec: Any) -> str | None:
        """Tier-2 path: create a ``Proposal`` placeholder.

        The placeholder carries the spec's identity (so the
        dashboard can list "proposals awaiting review" and link
        each one back to its spec) but no diff/rationale yet
        &mdash; those are filled in by the coordinator subagent
        as it works, which the ``Proposal`` row can be updated
        with later.

        Returns the new ``proposal_id``, or ``None`` if the
        ``ProposalStore`` isn't wired. The caller threads the id
        into the goal so the coordinator's kanban post can
        cross-reference it.
        """
        from harness.jobs.spec import _proposal_store
        from harness.store.protocols import ProposalRecord

        store = _proposal_store()
        if store is None:
            logger.debug(
                "tier-2 spec=%s accepted without ProposalStore; "
                "the work will still run, but the review queue has no record.",
                getattr(spec, "spec_id", "<unknown>"),
            )
            return None
        import uuid as _uuid
        proposal_id = str(_uuid.uuid4())
        record = ProposalRecord(
            proposal_id=proposal_id,
            spec_id=getattr(spec, "spec_id", ""),
            test_files=[],
            rationale="",
            risk_score=0,
            status="pending_review",
        )
        try:
            await store.save(record)
            logger.info(
                "tier-2 proposal created: proposal_id=%s spec_id=%s",
                proposal_id, record.spec_id,
            )
        except Exception as exc:
            logger.warning(
                "tier-2 proposal save failed (spec_id=%s): %s \u2014 "
                "continuing without persistence",
                record.spec_id, exc,
            )
            return None

        # Wire of C00-C-8 (CC7, Tembo Tasks-Inbox handoff). The
        # proposal was written to the durable store above; we
        # ALSO push a notification so the human reviewer sees
        # it in their configured channel without having to poll
        # the dashboard.
        try:
            from harness.memory.db_context import get_db as _get_db_for_notify
            from harness.notifications import dispatch as _notify_dispatch
            await _notify_dispatch(
                event_type="proposal:created",
                data={
                    "proposal_id": proposal_id,
                    "spec_id": record.spec_id,
                    "tier": getattr(spec, "tier", 2),
                    "prompt": (getattr(spec, "prompt", "") or "")[:280],
                    "repo": getattr(spec, "repo_url", ""),
                },
                db=_get_db_for_notify(),
            )
        except Exception as exc:
            logger.debug("tier-2 notification dispatch failed (non-fatal): %s", exc)

        return proposal_id

    @staticmethod
    async def human_authored_proposal(spec: Any) -> dict[str, Any]:
        """Tier-3 path: the orchestrator does NOT run the agent.

        Instead, it creates a kanban board with a single
        "awaiting human review" task carrying the spec's prompt.
        The user reviews the proposal and either approves
        (turning it into a tier-1 job via ``submit_job`` again)
        or rejects it.

        This keeps the chat &rarr; orchestrator boundary the same
        for all three tiers: a job submission is always a
        JobSpec, never a code execution directly. Tier 3 just
        means the execution step is gated on human approval.
        """
        from harness.tools.registry import registry
        board_id = None
        try:
            kanban_create = registry.get("kanban_create")
            if kanban_create:
                br = await kanban_create.run(
                    name=f"Tier-3 proposal: {spec.prompt[:80]}",
                    description=(
                        f"HUMAN-AUTHORED PROPOSAL \u2014 tier 3.\n\n"
                        f"Prompt: {spec.prompt}\n"
                        f"Repo: {spec.repo_url or '(not specified)'}\n"
                        f"Branch: {spec.branch or 'main'}\n"
                        f"Capabilities: {', '.join(spec.capabilities) or 'none'}\n\n"
                        f"The orchestrator did NOT run code for this "
                        f"submission. A human reviewer must:\n"
                        f"1. Read the spec's prompt\n"
                        f"2. Decide whether to re-submit as tier 1 (autonomous) "
                        f"or tier 2 (supervised) via submit_job\n"
                        f"3. Or close the kanban task as 'rejected'\n"
                    ),
                )
                if hasattr(br, "output"):
                    try:
                        board_id = json.loads(br.output).get("board_id")
                    except (json.JSONDecodeError, TypeError):
                        board_id = None
        except Exception:
            pass
        return {
            "success": True,
            "tier": 3,
            "capabilities": list(spec.capabilities),
            "human_authored": True,
            "board_id": board_id,
            "output": (
                f"Tier-3 proposal recorded. The orchestrator did not "
                f"execute any code. Review the proposal on the kanban "
                f"board (board_id={board_id}) and re-submit via "
                f"submit_job as tier 1 or tier 2 if you want the "
                f"work to run."
            ),
        }

"""Per-role round recipes for `Agent.run()`.

The C2-revised deepening of the architecture review proposed
extracting `Agent.run()` into a pipeline of typed `PipelineStep`
Protocols. The research summary in the work log showed that
no major agent harness (Hermes, SWE-agent, OpenHands, Claude
Code) does this — they all keep the round body as a single
method with pre/post hooks. So we adopt the simpler version:
a per-role list of method names to call at the top of each
round.

**Shape of the recipe.** The recipe is a list of method names
(strings). The method is called on the `Agent` instance via
`getattr(self, "_" + name)()`. The method must take no args
beyond `self`; it operates on `self._messages` and other Agent
state. The recipe is walked once per round, BEFORE the LLM
call, AFTER the interrupt check.

**Why per-role.** The chat surface drains background subagent
results at the top of each round (so a chat session that's
running a delegated worker sees the worker's progress between
turns). The orchestrator's coordinator is autonomous — there
is no human to drain background for, and no interactive
interrupt to handle. Today, every agent runs `_drain_background_
results()` regardless. The recipe makes the difference
explicit: chat's recipe is `["drain_background"]`; orchestrator's
is `[]`.

**Adding a new step.** A new concern is added in two steps:
1. Implement it as a method on `Agent` (e.g. `def _score_response
   (self) -> None`).
2. Add the method name to the recipes that should run it
   (e.g. `RECIPES["chat"] += ["score_response"]`).

Concerns that run after the LLM call (e.g. cost recording,
reflection) stay inline in `run()` — the recipe is for the
PRE-ROUND hooks only. Extracting post-LLM concerns to the
recipe would require restructuring the round body to return
intermediate state to the recipe walker, which is the
"pipeline of stages" the architecture review originally
proposed and which the field has shown isn't worth the
ceremony.
"""
from __future__ import annotations

from typing import Final


# Per-role recipes. Each entry is a list of method names
# (without the leading underscore) to call at the top of
# every round, BEFORE the LLM call, AFTER the interrupt
# check. The method is invoked on the Agent instance.
#
# Today the chat's only pre-round hook is draining background
# subagent results. The orchestrator's coordinator has no
# interactive human in the loop, so it has no pre-round hooks.
RECIPES: Final[dict[str, list[str]]] = {
    "chat": ["drain_background_results"],
    "orchestrator": [],
}


def resolve_recipe(name: str) -> list[str]:
    """Return the recipe for a role, falling back to chat.

    Unknown role names get the chat recipe rather than an
    empty list. The fallback matches the policy in
    `toolsets_for_mode`: any unrecognised agent role should
    default to the safe interactive surface.
    """
    return RECIPES.get(name, RECIPES["chat"])


__all__ = ["RECIPES", "resolve_recipe"]

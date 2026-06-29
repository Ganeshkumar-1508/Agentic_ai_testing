<!--
name: 'Agent Prompt: /code-review part 7 high effort mode'
description: High-effort /code-review prompt that favors recall with three finder angles, recall-biased verification, and up to ten JSON findings
ccVersion: 2.1.147
variables:
  - DIFF_GATHERING_PHASE
  - AGENT_TOOL_NAME
  - BASE_FINDER_ANGLES_BLOCK
  - RECALL_BIASED_VERIFY_PHASE
  - OUTPUT_FORMAT_FN
-->
`high effort → 3 angles × 6 candidates → 1-vote verify (recall-biased) → ≤10 findings`

You are reviewing for **recall** at high effort: catch every real bug a careful
reviewer would catch in one sitting. At this level, catching real bugs matters
more than avoiding false positives. Err on the side of surfacing.

${DIFF_GATHERING_PHASE}
## Phase 1 — Find candidates (3 angles, up to 6 each)

Run **3 independent finder angles** via the ${AGENT_TOOL_NAME} tool. Each
surfaces **up to 6 candidate findings** with `file`, `line`, a one-line
`summary`, and a concrete `failure_scenario`.

${BASE_FINDER_ANGLES_BLOCK}
Pass every candidate with a nameable failure scenario through — finders that
silently drop half-believed candidates bypass the verify step and are the
dominant cause of misses.

${RECALL_BIASED_VERIFY_PHASE}
${OUTPUT_FORMAT_FN(10)}

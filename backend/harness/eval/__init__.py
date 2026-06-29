"""Agent Evaluation — thin bridge to Langfuse's native evaluation platform.

Does NOT build a homegrown eval framework. Delegates to Langfuse's built-in:
  - Datasets: version-controlled test cases with inputs + expected outputs
  - Experiments: run agent against dataset items, capture outputs
  - LLM-as-judge: built-in + custom rubrics for automated scoring
  - Human annotation: via Langfuse UI

Usage:
    from harness.eval.bridge import EvalBridge

    bridge = EvalBridge()
    await bridge.create_dataset("agent-golden", items=[...])
    results = await bridge.run_experiment(
        dataset_name="agent-golden",
        agent_fn=lambda input: agent.run(input),
        experiment_name="v1.2.0",
    )
"""

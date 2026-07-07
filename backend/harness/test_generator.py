"""AI test case generation from requirements using LLM.

Analyzes requirements text and generates structured test cases
including edge cases, boundary conditions, and traceability.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from harness.prompt_builder import load_agent_prompt

logger = logging.getLogger(__name__)

# Load TDD agent prompt from ECC (battle-tested)
_TDD_PROMPT = load_agent_prompt("tdd-guide")

_FALLBACK_TDD_PROMPT = """You are a test case generator. Generate test cases as a JSON array.
Each element must be a JSON object with these exact keys: "id" (string like "TC-001"), "type" (one of "unit", "integration", "e2e"), "description" (string), "scenario" (string), "expectedBehavior" (string), "coverage" (string).
Output ONLY the JSON array. No markdown, no explanation, no code fences."""


async def generate_test_cases(requirements: str, llm: Any, count: int = 10) -> list[dict[str, Any]]:
    """Generate test cases from requirements using the configured LLM."""
    from harness.llm import ChatMessage

    system = _TDD_PROMPT or _FALLBACK_TDD_PROMPT
    prompt = f"{system}\n\n## Requirements\n{requirements}\n\nGenerate exactly {count} test cases as a JSON array. Each test case must be a JSON object with keys: id, type, description, scenario, expectedBehavior, coverage. Output ONLY the JSON array, nothing else."

    for attempt in range(3):
        try:
            response = await llm.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=4096,
            )
            content = (response.content or "").strip()
            logger.info("LLM response (attempt %d): %d chars", attempt + 1, len(content))

            if not content:
                logger.warning("LLM returned empty response (attempt %d)", attempt + 1)
                continue

            # Clean up markdown fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0].strip()

            test_cases = json.loads(content)
            if isinstance(test_cases, dict) and "test_cases" in test_cases:
                test_cases = test_cases["test_cases"]

            if not isinstance(test_cases, list):
                logger.warning("LLM returned non-list: %s", type(test_cases).__name__)
                continue

            return test_cases[:count]

        except json.JSONDecodeError as e:
            logger.warning("JSON parse failed (attempt %d): %s — content: %s", attempt + 1, e, content[:200] if 'content' in dir() else 'N/A')
            continue
        except Exception as e:
            logger.warning("Test generation failed (attempt %d): %s (%s)", attempt + 1, e, type(e).__name__)
            continue

    return []


async def save_test_cases(db: Any, project_id: str, requirement_id: str, test_cases: list[dict]) -> int:
    """Save generated test cases to the database."""
    saved = 0
    for tc in test_cases:
        try:
            await db.execute(
                """INSERT INTO test_cases
                   (project_id, requirement_id, name, description, test_type,
                    priority, steps, expected_result, status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending')""",
                project_id, requirement_id,
                tc.get("title", tc.get("name", "Untitled")),
                tc.get("description", ""),
                tc.get("test_type", "functional"),
                tc.get("priority", "medium"),
                json.dumps(tc.get("steps", [])),
                tc.get("expected_result", ""),
            )
            saved += 1
        except Exception as e:
            logger.warning("Failed to save test case: %s", e)
    return saved

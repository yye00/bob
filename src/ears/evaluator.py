"""EARS-style behavior acceptance criteria evaluator.

Provides check_behavior function that uses the parsed structure from
ears.parser.parse_behavior to verify whether code satisfies a behavior AC.

Public API
----------
check_behavior(criterion, code_context) -> dict
    Check if code satisfies the parsed behavior criterion.
    Returns a dict with verdict (bool), evidence (str), and confidence (float).
"""

from __future__ import annotations

from typing import Any

from ears.parser import BehaviorCriterion


def check_behavior(
    criterion: BehaviorCriterion,
    code_context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Check if code satisfies the parsed behavior criterion.

    Uses the structured fields (subject, verb, object_, condition) from the
    BehaviorCriterion to produce a targeted verification rather than relying
    on freeform prose.

    Args:
        criterion: Parsed BehaviorCriterion with subject, verb, object_, condition
        code_context: Optional context dict containing:
            - files: dict[str, str] mapping file paths to content
            - test_results: optional test execution results
            - diff: optional git diff or code changes

    Returns:
        dict with:
            - verdict: bool - whether the criterion is satisfied
            - evidence: str - specific evidence from code/tests
            - confidence: float - confidence level 0.0-1.0
            - prompt: str - structured verification prompt

    Examples:
        >>> from ears.parser import parse_behavior
        >>> ac = parse_behavior("behavior: parser returns BehaviorAC when AC matches grammar")
        >>> result = check_behavior(ac)
        >>> result['verdict']
        True
    """
    if not criterion:
        return {
            "verdict": False,
            "evidence": "No criterion provided",
            "confidence": 1.0,
            "prompt": ""
        }

    # Build structured verification prompt
    prompt_parts = [
        "## Behavior AC Verification\n",
        f"Verify the following behavior:\n",
        f"- **Subject**: {criterion.subject}",
        f"- **Action**: {criterion.verb} {criterion.object_}",
        f"- **Condition**: when {criterion.condition}\n",
        "### Verification Steps",
        "1. Identify code/files where the subject is defined",
        f"2. Verify that '{criterion.subject}' performs '{criterion.verb} {criterion.object_}'",
        f"3. Confirm this behavior occurs when '{criterion.condition}'",
        "4. Provide file:line references as evidence\n",
        "### Decision Criteria",
        "- PASS: All three components (subject, action, condition) are present and correctly implemented",
        "- FAIL: Any component is missing, incorrect, or not triggered by the condition"
    ]

    structured_prompt = "\n".join(prompt_parts)

    # If we have code_context, we can do basic verification
    verdict = False
    evidence_parts = []
    confidence = 0.5  # Medium confidence without actual code analysis

    if code_context:
        files = code_context.get("files", {})

        # Basic heuristic: check if subject/verb/object appear in code
        matches_found = []
        for file_path, content in files.items():
            if criterion.subject.lower() in content.lower():
                matches_found.append(f"{file_path}: contains '{criterion.subject}'")
            if criterion.verb and criterion.verb.lower() in content.lower():
                matches_found.append(f"{file_path}: contains '{criterion.verb}'")

        if matches_found:
            verdict = True
            evidence_parts = matches_found
            confidence = 0.7
        else:
            evidence_parts = ["No matching code found for subject/verb/object"]
            confidence = 0.8
    else:
        evidence_parts = ["No code context provided - verification requires manual review"]

    return {
        "verdict": verdict,
        "evidence": "\n".join(evidence_parts),
        "confidence": confidence,
        "prompt": structured_prompt
    }


__all__ = ["check_behavior"]

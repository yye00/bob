"""Independent plan-review agent for Bob (Gap #6).

Provides ``review_plan(plan, feature) -> PlanReview``.  After the planning
phase produces a plan but before the implementation sub-agent is spawned,
a separate haiku-grade agent reviews the plan against the spec and checks
for spec misreads, missing acceptance-criteria coverage, over-ambitious
scope (>200 LOC estimate), and risky patterns such as direct file deletion
or unconditional rewrites of existing code.

If any blocker is found, the plan is returned to the planning agent for
revision (max 2 revision cycles are managed by the caller).

PlanReview includes: verdict (approve/revise/block), findings list,
confidence score.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from bob73.integration_checker import check_reachability  # noqa: F401 – integration wiring

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_VALID_VERDICTS: frozenset[str] = frozenset({"approve", "revise", "block"})


class PlanReview(BaseModel):
    """Structured verdict from the independent plan-review agent.

    verdict:
        - ``approve``: the plan is safe to hand to the implementation
          sub-agent as-is.
        - ``revise``: the plan has issues that can be corrected; return
          it to the planning agent for revision (max 2 cycles).
        - ``block``: the plan has a hard blocker (e.g. destructive
          patterns, fundamental spec misread) that warrants human review.
    findings:
        Free-text list of issues found. Should be actionable.
    confidence:
        Reviewer's self-rated confidence in the verdict on [0.0, 1.0].
    """

    verdict: Literal["approve", "revise", "block"]
    findings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("verdict", mode="before")
    @classmethod
    def _validate_verdict(cls, v: str) -> str:
        if v not in _VALID_VERDICTS:
            raise ValueError(f"verdict must be one of {_VALID_VERDICTS}, got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

_SAFE_DEFAULT: dict[str, Any] = {
    "verdict": "revise",
    "findings": ["Plan review response could not be parsed; treating as revise."],
    "confidence": 0.0,
}


def parse_plan_review(response_text: str) -> dict[str, Any]:
    """Parse a haiku reviewer's response into a dict matching PlanReview.

    Looks for a fenced ``json`` block first, then any inline JSON object
    containing a ``verdict`` key.  On any parse failure returns a safe
    default of ``revise`` with confidence=0.0 so the plan is revised
    rather than silently approved.
    """
    fenced = re.search(r"```json\s*\n?(.*?)\n?\s*```", response_text, re.DOTALL)
    json_str: str | None = fenced.group(1) if fenced else None

    if json_str is None:
        inline = re.search(r'\{[^{}]*"verdict"[^{}]*\}', response_text, re.DOTALL)
        json_str = inline.group(0) if inline else None

    if json_str is None:
        return dict(_SAFE_DEFAULT)

    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return dict(_SAFE_DEFAULT)

    if not isinstance(parsed, dict):
        return dict(_SAFE_DEFAULT)

    verdict = parsed.get("verdict")
    if verdict not in _VALID_VERDICTS:
        return dict(_SAFE_DEFAULT)

    findings_raw = parsed.get("findings") or []
    if not isinstance(findings_raw, list):
        findings_raw = [str(findings_raw)]
    findings = [str(f) for f in findings_raw]

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "verdict": verdict,
        "findings": findings,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Haiku reviewer prompt
# ---------------------------------------------------------------------------

_REVIEWER_SYSTEM_PROMPT = (
    "You are an independent plan-review agent. Your job is to review an "
    "implementation plan BEFORE any code is written. You do NOT write code. "
    "You check the plan for four categories of problems:\n\n"
    "1. SPEC MISREADS: does the plan misinterpret the feature description?\n"
    "2. MISSING AC COVERAGE: does the plan fail to address all acceptance "
    "criteria listed in the feature?\n"
    "3. OVER-AMBITIOUS SCOPE: does the plan estimate more than 200 lines of "
    "code? If so, it is too large and must be revised.\n"
    "4. RISKY PATTERNS: does the plan include direct file deletion, "
    "unconditional rewrites of existing code, or other destructive operations "
    "without explicit justification?\n\n"
    "Return ONLY a JSON object inside a ```json fence with fields:\n"
    "  verdict: 'approve' | 'revise' | 'block'\n"
    "  findings: list of strings (empty on approve)\n"
    "  confidence: float in [0.0, 1.0]\n\n"
    "Use 'block' only for hard blockers (destructive patterns, fundamental "
    "spec misread). Use 'revise' for fixable issues. Use 'approve' when the "
    "plan is sound and within scope.\n"
    "No other output — only the JSON fence."
)


def _build_review_prompt(plan: str, feature: dict[str, Any]) -> str:
    name = feature.get("name", "(unnamed feature)")
    description = feature.get("description") or "(no description)"
    ac_raw = feature.get("acceptance_criteria") or "[]"

    if isinstance(ac_raw, str):
        try:
            ac_list = json.loads(ac_raw)
            if isinstance(ac_list, list):
                ac_text = "\n".join(f"- {c}" for c in ac_list)
            else:
                ac_text = str(ac_raw)
        except (json.JSONDecodeError, ValueError):
            ac_text = ac_raw
    elif isinstance(ac_raw, list):
        ac_text = "\n".join(f"- {c}" for c in ac_raw)
    else:
        ac_text = str(ac_raw)

    return (
        f"## Feature: {name}\n\n"
        f"### Description\n{description}\n\n"
        f"### Acceptance Criteria\n{ac_text}\n\n"
        f"### Implementation Plan\n{plan}\n\n"
        "Review the plan against the spec and acceptance criteria. "
        "Return your verdict as described in the system prompt."
    )


# ---------------------------------------------------------------------------
# Internal runner (isolated for easy mocking in tests)
# ---------------------------------------------------------------------------


async def _run_haiku_review(prompt: str) -> str:
    """Run a haiku-grade Claude review and return its raw text response.

    Uses the claude-code-sdk query() interface directly (not spawn_sub_agent)
    since this is a lightweight, stateless analysis call that does not need
    file-system access or tool use.
    """
    from claude_code_sdk import ClaudeCodeOptions, query, TextBlock

    from bob.orchestrator.claude_executor import _FORCE_THINKING_ENV, _FORCE_THINKING_SETTINGS

    options = ClaudeCodeOptions(
        model="haiku",
        max_turns=3,
        system_prompt=_REVIEWER_SYSTEM_PROMPT,
        allowed_tools=[],
        settings=_FORCE_THINKING_SETTINGS,  # F-R6-311
        env=dict(_FORCE_THINKING_ENV),  # F-R6-311 (env override)
    )

    accumulated: list[str] = []
    async for message in query(prompt=prompt, options=options):
        from claude_code_sdk import AssistantMessage
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    accumulated.append(block.text)

    return "\n".join(accumulated)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def review_plan(plan: str, feature: dict[str, Any]) -> PlanReview:
    """Review an implementation plan with a haiku-grade agent.

    Args:
        plan: The implementation plan text produced by the planning phase.
        feature: Feature dict (or Feature model's __dict__) containing at
            minimum ``name``, ``description``, and ``acceptance_criteria``.

    Returns:
        PlanReview with verdict, findings, and confidence.
        - ``approve``: plan is ready for implementation.
        - ``revise``: plan needs revision before implementation.
        - ``block``: plan has a hard blocker requiring human review.
    """
    prompt = _build_review_prompt(plan, feature)
    try:
        raw = await _run_haiku_review(prompt)
    except Exception as exc:
        logger.warning("Plan reviewer sub-agent failed: %s", exc)
        return PlanReview(
            verdict="revise",
            findings=[f"Plan reviewer failed: {exc}"],
            confidence=0.0,
        )

    parsed = parse_plan_review(raw)
    return PlanReview(**parsed)

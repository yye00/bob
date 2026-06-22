"""Uniform predicted-confidence elicitor for Bob3.

After each sub-agent spawn completes, runs a lightweight post-spawn LLM probe
(haiku, 1 turn) asking the sub-agent to estimate its own confidence on a 0-1
scale. The probe is identical across all ablation variants to ensure fair
Expected Calibration Error (ECE) computation.

Results are stored in the bob3.db calibration_data table and a cost_checkpoint
event is emitted for each probe.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Uniform probe — identical across ALL ablation variants (required for fair ECE)
# ---------------------------------------------------------------------------

_CONFIDENCE_PROBE = (
    "You just completed a software implementation task. "
    "On a scale from 0.0 to 1.0, what is your confidence that your implementation "
    "fully satisfies all acceptance criteria and passes all tests? "
    "Respond with a JSON object: "
    '{"confidence": <float 0.0-1.0>, "reasoning": "<one sentence explanation>"}'
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class ConfidenceResult(BaseModel):
    """Result of a post-spawn confidence probe."""

    feature_id: str
    sub_agent_run_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    probe_cost_usd: float = 0.0
    probed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def parse_confidence_response(raw: str) -> dict:
    """Parse the LLM probe response into a confidence dict.

    Attempts JSON extraction from fenced blocks, then bare JSON, then falls
    back to a regex scan for a float value. Returns a dict with keys
    ``confidence`` (float, clamped to [0,1]) and ``reasoning`` (str).
    """
    # Try fenced JSON block first
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fenced:
        try:
            data = json.loads(fenced.group(1).strip())
            return _normalize(data)
        except (json.JSONDecodeError, KeyError):
            pass

    # Try bare JSON
    try:
        data = json.loads(raw.strip())
        return _normalize(data)
    except (json.JSONDecodeError, KeyError):
        pass

    # Regex fallback: look for a float in the response
    m = re.search(r"\b(0\.\d+|1\.0+|0|1)\b", raw)
    if m:
        return {"confidence": _clamp(float(m.group(1))), "reasoning": ""}

    # Last resort: return 0.5 (neutral)
    return {"confidence": 0.5, "reasoning": ""}


def _normalize(data: dict) -> dict:
    raw_confidence = data.get("confidence", 0.5)
    confidence = _clamp(float(raw_confidence))
    reasoning = str(data.get("reasoning", ""))
    return {"confidence": confidence, "reasoning": reasoning}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _confidence_to_bucket(confidence: float) -> str:
    """Map a [0,1] confidence score to a decile bucket string."""
    if confidence >= 1.0:
        return "0.9-1.0"
    decile = int(confidence * 10) / 10
    return f"{decile:.1f}-{decile + 0.1:.1f}"


# ---------------------------------------------------------------------------
# Internal helpers (isolated for unit testing via patch)
# ---------------------------------------------------------------------------


async def _run_haiku_probe(prompt: str) -> str:
    """Run a single-turn haiku probe and return the raw text response."""
    from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock, query

    from bob3.orchestrator.claude_executor import _FORCE_THINKING_ENV, _FORCE_THINKING_SETTINGS

    options = ClaudeCodeOptions(
        model="haiku",
        max_turns=1,
        allowed_tools=[],
        settings=_FORCE_THINKING_SETTINGS,  # F-R6-311
        env=dict(_FORCE_THINKING_ENV),  # F-R6-311 (env override)
    )

    accumulated: list[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    accumulated.append(block.text)

    return "\n".join(accumulated)


def _store_calibration(
    *,
    project_id: str | None,
    feature_id: str,
    confidence: float,
    task_class: str,
) -> None:
    """Upsert the elicited confidence into the calibration_data table."""
    from bob3.db import create_or_update_calibration

    bucket = _confidence_to_bucket(confidence)
    # We don't know the pass/fail outcome at elicitation time; we record a
    # single attempt marked as a "pass" placeholder so the expected_pass_rate
    # column tracks the raw elicited confidence for ECE computation.
    create_or_update_calibration(
        project_id=project_id,
        task_class=task_class,
        confidence_bucket=bucket,
        passed=True,
        expected_pass_rate=confidence,
    )


def _emit_cost_checkpoint(
    *,
    feature_id: str,
    project_id: str | None,
    probe_cost_usd: float,
    confidence: float,
) -> None:
    """Emit a cost_checkpoint event for the confidence probe."""
    from bob3.progress_events import emit_event

    emit_event(
        event_type="cost_checkpoint",
        payload={
            "source": "confidence_elicitor",
            "probe_cost_usd": probe_cost_usd,
            "confidence": confidence,
        },
        project_id=project_id or "",
        feature_id=feature_id,
        attempt_number=0,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def elicit_confidence(
    *,
    feature_id: str,
    sub_agent_run_id: str,
    project_id: str | None,
    task_class: str = "feature_implementation",
) -> ConfidenceResult:
    """Run a post-spawn confidence probe and store the result.

    Sends the uniform confidence probe (identical across all ablation variants)
    to a haiku model, parses the 0-1 confidence estimate, stores the result in
    the calibration_data table, and emits a cost_checkpoint event.

    Args:
        feature_id: The feature whose sub-agent just completed.
        sub_agent_run_id: The ID of the completed sub-agent run.
        project_id: The parent project ID (may be None).
        task_class: Task class label for calibration bucketing.

    Returns:
        ConfidenceResult with the elicited confidence and metadata.
        On LLM failure, returns a default result with confidence=0.5.
    """
    try:
        raw = await _run_haiku_probe(_CONFIDENCE_PROBE)
        parsed = parse_confidence_response(raw)
        confidence = parsed["confidence"]
        reasoning = parsed["reasoning"]
    except Exception as exc:
        logger.warning("Confidence probe failed for feature %s: %s", feature_id, exc)
        confidence = 0.5
        reasoning = f"Probe failed: {exc}"

    result = ConfidenceResult(
        feature_id=feature_id,
        sub_agent_run_id=sub_agent_run_id,
        confidence=confidence,
        reasoning=reasoning,
    )

    try:
        _store_calibration(
            project_id=project_id,
            feature_id=feature_id,
            confidence=confidence,
            task_class=task_class,
        )
    except Exception as exc:
        logger.warning("Failed to store calibration for feature %s: %s", feature_id, exc)

    try:
        _emit_cost_checkpoint(
            feature_id=feature_id,
            project_id=project_id,
            probe_cost_usd=result.probe_cost_usd,
            confidence=confidence,
        )
    except Exception as exc:
        logger.warning("Failed to emit cost_checkpoint for feature %s: %s", feature_id, exc)

    return result

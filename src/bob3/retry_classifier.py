"""Retry classifier for evaluator MCP-transient failures (F-R7-597).

Provides :func:`classify_evaluator_result` as the public API for detecting
evaluator sub-agent crashes caused by MCP/TLS infrastructure noise rather than
real feature-correctness failures.

The implementation delegates to :func:`bob3.run_loop.classify_evaluator_mcp_transient`,
which owns the token list and retry-cap logic. This module is the canonical
importable entry point so that code outside run_loop can call the classifier
without a circular dependency.
"""

from __future__ import annotations

from typing import Any

from bob3.run_loop import classify_evaluator_mcp_transient


def classify_evaluator_result(
    *,
    verdict: str | None,
    confidence: float | None,
    is_error: bool,
    stderr: str | None,
    feature_id: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Classify an evaluator result as MCP-transient, mcp_persistent, or not_transient.

    This is the public API entry point defined in ``bob3.retry_classifier``
    (AC: "Function defined: bob3.retry_classifier.classify_evaluator_result").
    It delegates all logic to :func:`bob3.run_loop.classify_evaluator_mcp_transient`.

    Parameters
    ----------
    verdict:
        Evaluator verdict string. Only ``"INSUFFICIENT_EVIDENCE"`` can trigger
        the MCP-transient path; any other value returns ``not_transient``.
    confidence:
        Evaluator confidence score. Must be ``0.0`` (or ``None``) for the
        MCP-transient path to activate.
    is_error:
        Whether the evaluator sub-agent exited with ``is_error=True``.
    stderr:
        Captured stderr text from the evaluator sub-agent. May be ``None``.
    feature_id:
        Optional feature UUID; echoed in the return dict and log events.
    retry_count:
        Number of MCP-transient re-readies already fired for this feature in
        the current round. Must be an ``int``; raises ``ValueError`` otherwise.

    Returns
    -------
    dict with keys:
        classification: ``"mcp_transient"`` | ``"mcp_persistent"`` | ``"not_transient"``
        matched_token: str | None
        event: str
        feature_id: str | None
        retry_count_after: int

    Raises
    ------
    ValueError
        When ``retry_count`` is not an integer.
    """
    return classify_evaluator_mcp_transient(
        verdict=verdict,
        confidence=confidence,
        is_error=is_error,
        stderr=stderr,
        feature_id=feature_id,
        retry_count=retry_count,
    )


def classify_evaluator_failure(
    *,
    verdict: str | None,
    confidence: float | None,
    is_error: bool,
    stderr: str | None,
    feature_id: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Classify an evaluator failure as MCP-transient, mcp_persistent, or not_transient.

    AC alias: "Function defined: bob3.retry_classifier.classify_evaluator_failure".
    Delegates to :func:`classify_evaluator_result`.
    """
    return classify_evaluator_result(
        verdict=verdict,
        confidence=confidence,
        is_error=is_error,
        stderr=stderr,
        feature_id=feature_id,
        retry_count=retry_count,
    )

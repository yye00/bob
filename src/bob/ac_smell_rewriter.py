"""AC smell rewriter with semantic-equivalence verification.

This module provides the public API for applying suggested rewrites to smelly
acceptance criteria, with LLM-based semantic equivalence verification.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

Public API::

    from bob.ac_smell_rewriter import apply_suggested_rewrite, verify_semantic_equivalence

    is_equiv, rationale = verify_semantic_equivalence(original, rewrite)

    updated_ac, was_applied = apply_suggested_rewrite(
        finding,
        auto_repair=True,
    )
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.ac_auto_repair import (
    verify_semantic_equivalence as _verify_semantic_equivalence,
    suggest_rewrite,
    EquivalenceJudgeUnavailableError,
    RewriteRejectedError,
)
from bob.spec_quality.smell_detectors import SmellFinding

__all__ = [
    "apply_suggested_rewrite",
    "verify_semantic_equivalence",
    "EquivalenceJudgeUnavailableError",
    "RewriteRejectedError",
    "SmellFinding",
]


def verify_semantic_equivalence(original: str, rewrite: str) -> tuple[bool, str]:
    """Verify that *rewrite* is semantically equivalent to *original* via an LLM judge.

    Parameters
    ----------
    original:
        The original acceptance-criterion text.
    rewrite:
        The proposed rewrite to check for equivalence.

    Returns
    -------
    tuple[bool, str]
        ``(is_equivalent, rationale)`` — if the judge cannot be reached or the
        response cannot be parsed, returns ``(False, error_message)``.

    Raises
    ------
    ValueError
        If *original* or *rewrite* is not a non-empty string.
    """
    if not isinstance(original, str) or not original.strip():
        raise ValueError("original must be a non-empty string")
    if not isinstance(rewrite, str) or not rewrite.strip():
        raise ValueError("rewrite must be a non-empty string")

    return _verify_semantic_equivalence(original, rewrite)


def apply_suggested_rewrite(
    finding: SmellFinding,
    *,
    auto_repair: bool = True,
) -> tuple[str, bool]:
    """Apply the suggested rewrite for a smell *finding* if it passes equivalence.

    Workflow:
    1. If *auto_repair* is ``False``, return the original text unchanged.
    2. Only ERROR-severity findings are auto-applied; WARN/INFO are skipped.
    3. Generate a suggested rewrite via the linter.
    4. Verify semantic equivalence via ``verify_semantic_equivalence``.
    5. If equivalent, return the rewrite; otherwise return the original.

    Parameters
    ----------
    finding:
        A :class:`~bob.spec_quality.smell_detectors.SmellFinding` produced by
        the smell detector.
    auto_repair:
        When ``False``, no rewrite is applied regardless of severity or
        equivalence (per-feature opt-out).

    Returns
    -------
    tuple[str, bool]
        ``(ac_text, was_applied)`` — the (possibly rewritten) AC text and a
        flag indicating whether the rewrite was applied.

    Raises
    ------
    ValueError
        If *finding* is not a :class:`SmellFinding` instance.
    """
    if not isinstance(finding, SmellFinding):
        raise ValueError(f"finding must be a SmellFinding instance, got {type(finding)!r}")

    if not auto_repair:
        return finding.text, False

    if finding.severity != "E":
        return finding.text, False

    rewrite = suggest_rewrite(finding)
    if rewrite is None:
        return finding.text, False

    is_equiv, _rationale = verify_semantic_equivalence(finding.text, rewrite)
    if not is_equiv:
        return finding.text, False

    return rewrite, True

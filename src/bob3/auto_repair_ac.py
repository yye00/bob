"""Auto-repair of smelly ACs with semantic-equivalence verification.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

Public API::

    from bob3.auto_repair_ac import repair_with_equivalence_check, should_auto_apply_rewrite

    is_equiv, rationale = repair_with_equivalence_check(original, rewrite)

    should_apply = should_auto_apply_rewrite(finding, auto_repair=True)

Integration with bob3.linter::

    from bob3.linter import detect_smells
    from bob3.auto_repair_ac import repair_with_equivalence_check, should_auto_apply_rewrite

    findings = detect_smells(ac_text)
    for finding in findings:
        if should_auto_apply_rewrite(finding):
            is_equiv, rationale = repair_with_equivalence_check(
                finding["text"], finding["suggested_rewrite"]
            )
"""

from __future__ import annotations

from typing import Any

from bob3.linter_ac_repair import (
    auto_repair_ac as _auto_repair_ac,
    semantic_equivalence_check as _semantic_equivalence_check,
)


def repair_with_equivalence_check(
    original: str,
    rewrite: str,
) -> tuple[bool, str]:
    """Check whether rewrite is semantically equivalent to original via LLM judge.

    Feeds original + rewrite to a separate LLM judge. If the judge cannot infer
    they impose the same observable constraint, returns (False, rationale).

    Parameters
    ----------
    original:
        The original acceptance criterion text.
    rewrite:
        The rewritten acceptance criterion text.

    Returns
    -------
    tuple[bool, str]
        (is_equivalent, rationale). On any LLM error returns (False, error_message).

    Raises
    ------
    ValueError
        If either argument is not a string.
    """
    return _semantic_equivalence_check(original, rewrite)


def should_auto_apply_rewrite(
    finding: dict[str, Any],
    auto_repair: bool = True,
) -> bool:
    """Determine whether a finding's rewrite should be auto-applied.

    A rewrite is eligible for auto-application when:
    - ``auto_repair`` is True (per-feature opt-out respects False)
    - The finding severity is ERROR ("E")
    - The finding has a non-None ``suggested_rewrite``

    Note: this function does NOT perform the equivalence check. Use
    ``repair_with_equivalence_check`` to confirm equivalence before applying.

    Parameters
    ----------
    finding:
        A smell finding dict (or SmellFinding namedtuple) with keys:
        severity, suggested_rewrite.
    auto_repair:
        When False, always returns False (per-feature opt-out).

    Returns
    -------
    bool
        True when the rewrite is eligible for auto-application.

    Raises
    ------
    ValueError
        If finding is not a dict-like object.
    """
    if not auto_repair:
        return False

    if hasattr(finding, "_asdict"):
        f: dict[str, Any] = finding._asdict()
    elif hasattr(finding, "__dict__"):
        f = {k: v for k, v in vars(finding).items() if not k.startswith("_")}
    elif isinstance(finding, dict):
        f = finding
    else:
        raise ValueError(f"finding must be a dict or named object, got {type(finding).__name__}")

    return f.get("severity") == "E" and f.get("suggested_rewrite") is not None


__all__ = [
    "repair_with_equivalence_check",
    "should_auto_apply_rewrite",
]

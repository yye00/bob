"""Auto-repair of smelly ACs with semantic-equivalence verification (hippy).

Per-smell, the linter emits a ``suggested_rewrite``. A semantic-equivalence
check feeds the original + rewrite to a separate LLM judge; if it cannot infer
they impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied. Per-feature
opt-out via ``auto_repair=False``.

Public API::

    from hippy.auto_repair import verify_semantic_equivalence, auto_apply_rewrites

    is_equiv, rationale = verify_semantic_equivalence(original, rewrite)

    result = auto_apply_rewrites(
        feature_id="feat-001",
        findings=[...],
        original_acs=["The system should process requests."],
    )
    result["repaired_acs"]     # list of (possibly repaired) ACs
    result["repairs_applied"]  # list of repair dicts

The heavy lifting is delegated to the tested top-level :mod:`auto_repair`
module so behaviour stays identical across both entry points.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import auto_repair as _auto_repair
from auto_repair import (  # re-exported for callers that patch the judge
    _call_llm_judge,
    _parse_equivalence_response,
)

__all__ = [
    "verify_semantic_equivalence",
    "auto_apply_rewrites",
    "_call_llm_judge",
    "_parse_equivalence_response",
]


def verify_semantic_equivalence(original: str, rewrite: str) -> tuple[bool, str]:
    """Return ``(is_equivalent, rationale)`` for *original* vs *rewrite*.

    A rewrite is accepted only when a separate LLM judge can infer that both
    texts impose the same observable constraint. Any judge failure or
    unparseable response yields ``(False, <reason>)`` so a bad rewrite is never
    silently applied.

    Raises
    ------
    ValueError
        If either argument is not a string.
    """
    return _auto_repair.semantic_equivalence_check(original, rewrite)


def auto_apply_rewrites(
    feature_id: str,
    findings: list[dict[str, Any]],
    original_acs: list[str],
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Auto-apply ERROR-severity rewrites that pass the equivalence check.

    Only findings with ``severity == "E"`` and a non-``None``
    ``suggested_rewrite`` are considered, and each candidate rewrite must pass
    :func:`verify_semantic_equivalence` before it is applied. Set
    ``auto_repair=False`` for the per-feature opt-out.

    Returns
    -------
    dict with keys ``repaired_acs`` (list[str]) and ``repairs_applied``
    (list[dict]).

    Raises
    ------
    ValueError
        If *feature_id* is not a string, or *findings* / *original_acs* are not
        lists.
    """
    return _auto_repair.apply_error_severity_rewrites(
        feature_id=feature_id,
        findings=findings,
        original_acs=original_acs,
        repairs_log=repairs_log,
        auto_repair=auto_repair,
    )

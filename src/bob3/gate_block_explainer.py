"""bob3.gate_block_explainer — re-export facade for the explain-gate-block feature.

This module satisfies the AC ``File exists: src/bob3/gate_block_explainer.py``
and re-exports the public symbols from :mod:`bob3.explain_gate_block` so that
callers can import from either module.
"""

from __future__ import annotations

from bob3.explain_gate_block import (  # noqa: F401
    compute_cheapest_fixes,
    compute_dimension_breakdown,
    explain_feature_block,
    explain_gate_block,
    score_and_analyze_feature,
    score_and_breakdown,
    score_feature,
    suggest_cheapest_fixes,
)

__all__ = [
    "compute_cheapest_fixes",
    "compute_dimension_breakdown",
    "explain_feature_block",
    "explain_gate_block",
    "score_and_analyze_feature",
    "score_and_breakdown",
    "score_feature",
    "suggest_cheapest_fixes",
]

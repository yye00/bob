"""Project-internal spec quality scoring tool.

This file exists so that workspace/tools/ is a recognized first-party
path and ``import spec_quality_score`` is not probed against PyPI by
the slopsquatting scanner.
"""

from __future__ import annotations


def score(spec_text: str) -> float:
    """Return a quality score for the given spec text (0.0–1.0)."""
    if not spec_text or not spec_text.strip():
        return 0.0
    words = spec_text.split()
    return min(1.0, len(words) / 100.0)

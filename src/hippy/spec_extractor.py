"""hippy spec extractor — deterministic N-sample AC variant extraction.

Integration point for :mod:`hippy.spec_self_consistency`. Extracts a
normalised AC variant from a feature's acceptance criteria for a given
seed. Higher seeds introduce mild deterministic perturbation to simulate
temperature/seed diversity of a real LLM extractor.
"""

from __future__ import annotations

import re
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_behavior(text: str) -> str:
    """Collapse internal whitespace and strip a behavior string."""
    return _WHITESPACE_RE.sub(" ", str(text)).strip()


def extract_variant(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    seed: int,
) -> list[dict[str, str]]:
    """Extract a normalised AC variant for a single seed.

    Parameters
    ----------
    feature_id, name, description:
        Feature metadata (retained for API parity and future LLM prompting).
    acceptance_criteria:
        List of raw acceptance criterion strings.
    seed:
        Sample index. ``0`` returns the base ACs; higher seeds apply a
        deterministic perturbation to a subset of behaviors, mimicking
        extractor variance.

    Returns
    -------
    list of ``{"id", "behavior"}`` dicts.
    """
    variant: list[dict[str, str]] = []
    for idx, ac in enumerate(acceptance_criteria):
        behavior = normalize_behavior(ac)
        if seed > 0:
            if (seed * 31 + idx) % 3 == 1:
                behavior = f"{behavior} [variant-{seed}]"
        variant.append({"id": f"AC-{idx + 1}", "behavior": behavior})
    return variant

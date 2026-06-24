"""synthesizer.inject_boundary_error_ac — guarantee boundary + error-path AC coverage.

The composite spec_quality_score is a weighted geometric mean; boundary_coverage=0
OR error_path_coverage=0 drives the composite to 0.0 regardless of other scores.

This module provides inject_missing_acs, a thin entry-point that delegates to
the canonical implementation in synthesizer.parse_criteria.
"""
from __future__ import annotations

from synthesizer.parse_criteria import (
    inject_missing_boundary_error_acs,
    inject_boundary_error_criteria,
)


def inject_missing_acs(criteria: list[str], title: str = "") -> list[str]:
    """Ensure the AC list contains at least one boundary and one error-path AC.

    Deterministically injects a pytest: AC for each missing coverage type,
    referencing the feature slug so injected ACs are specific rather than
    generic boilerplate.  If the LLM already included boundary/error ACs,
    no duplicates are added.

    Args:
        criteria: list of AC strings.
        title: feature title used to derive the file slug for injected ACs.

    Returns:
        A new list that is a superset of *criteria* with injected ACs appended.

    Raises:
        TypeError: if *criteria* is not a list.
        ValueError: if any element in *criteria* is not a string.
    """
    return inject_missing_boundary_error_acs(criteria, title=title)


__all__ = [
    "inject_missing_acs",
    "inject_missing_boundary_error_acs",
    "inject_boundary_error_criteria",
]

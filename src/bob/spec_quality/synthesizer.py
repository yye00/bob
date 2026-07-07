"""bob.spec_quality.synthesizer — parity anti-cheat hook for AC synthesis.

Feature 8ff7325a-aab0-43f3-89e9-ce039e624cee.

This is the spec_quality-side integration seam for the parity-test anti-cheat
(see :mod:`bob.spec_quality.parity_test_anti_cheat`). When the AC synthesizer
emits criteria for a feature whose intent is output-equals-reference, this hook
ensures the criteria carry a randomized-seed parity AC (and, where an execution
substrate is observable, an execution-evidence AC) so a single frozen-input
test cannot be gamed.

It never weakens an existing structural AC — it only appends the recognized
randomized parity AC shape when the intent is parity-shaped and no such AC is
already present.

Public API
----------
apply_parity_anti_cheat(criteria, *, title="", description="", num_seeds=32)
    -> list[str]
    Post-process a synthesized AC list: append a randomized parity AC when the
    combined title+description signals a parity/equivalence intent.
"""

from __future__ import annotations

from bob.spec_quality.parity_test_anti_cheat import (
    ensure_randomized_parity_coverage,
    is_parity_intent,
    synthesize_parity_ac,
)

__all__ = [
    "apply_parity_anti_cheat",
    "ensure_randomized_parity_coverage",
    "is_parity_intent",
    "synthesize_parity_ac",
]


def apply_parity_anti_cheat(
    criteria: list[str],
    *,
    title: str = "",
    description: str = "",
    num_seeds: int = 32,
) -> list[str]:
    """Append a randomized parity AC to *criteria* for a parity-shaped feature.

    The feature intent is the combined *title* and *description*. When that
    intent is output-equals-reference and *criteria* lacks a randomized parity
    AC, this appends the recognized shape from
    :func:`~bob.spec_quality.parity_test_anti_cheat.synthesize_parity_ac`.
    Existing structural ACs are always preserved.

    Raises
    ------
    ValueError
        If *criteria* is not a list of str, or *title* / *description* are not
        strings (propagated from :func:`ensure_randomized_parity_coverage`).
    """
    if not isinstance(title, str):
        raise ValueError(f"title must be a str, got {type(title).__name__!r}")
    if not isinstance(description, str):
        raise ValueError(
            f"description must be a str, got {type(description).__name__!r}"
        )
    intent = f"{title}\n{description}".strip()
    return ensure_randomized_parity_coverage(
        criteria, intent=intent, num_seeds=num_seeds
    )

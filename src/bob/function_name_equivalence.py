"""F-da4f09fc: Synthesizer MUST NOT invent exact function names it then
hard-gates on.

A ``Function defined: <module>.<symbol>`` acceptance criterion is contractual
only when ``<symbol>`` appears verbatim in the feature's prose. When the prose
merely describes a behavior and never names a concrete symbol, the synthesizer
is guessing an internal helper name the author never wrote — and a one-word
naming difference (e.g. ``apply_`` vs ``handle_``) then hard-fails an
otherwise-complete feature (the 99b78f59 drain).

This module is the single public surface tying together the two halves of the
fix:

* HALF 1 — synthesis: :func:`should_emit_function_ac` (from
  :mod:`bob.spec_synthesizer`) only warrants a ``Function defined:`` AC when the
  symbol appears verbatim in the prose.
* HALF 2 — verification: :func:`concept_token_match` (from
  :mod:`bob.enhanced_verification`) treats a synthesizer-invented name as
  satisfied-by-equivalent when a defined function shares the salient concept
  tokens of the demanded symbol.

Both are re-exported here so callers have one import point for the
function-name-equivalence policy.
"""
from __future__ import annotations

from bob.spec_synthesizer import should_emit_function_ac
from bob.enhanced_verification import (
    concept_token_match,
    check_function_name_equivalence,
)

__all__ = [
    "should_emit_function_ac",
    "concept_token_match",
    "check_function_name_equivalence",
    "is_function_ac_contractual",
    "is_satisfied_by_equivalent",
]


def is_function_ac_contractual(symbol: str, description: str) -> bool:
    """Return True iff a ``Function defined: …<symbol>`` AC is contractual.

    An AC is contractual only when *symbol* appears verbatim in the feature's
    prose *description*. Otherwise the synthesizer invented the name and the AC
    must be advisory (verified by behavior/equivalence, not exact match).

    Thin delegate to :func:`should_emit_function_ac` (HALF 1).
    """
    return should_emit_function_ac(symbol, description)


def is_satisfied_by_equivalent(demanded: str, candidate: str) -> bool:
    """Return True iff *candidate* satisfies *demanded* by concept-token match.

    Used by verification to demote an invented ``Function defined:`` AC to
    PASS-with-WARNING rather than hard-fail when the module defines a function
    sharing the demanded symbol's salient concept tokens.

    Thin delegate to :func:`concept_token_match` (HALF 2).
    """
    return concept_token_match(demanded, candidate)

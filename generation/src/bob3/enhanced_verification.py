"""Generation-layer shim for enhanced_verification 'Class defined:' AC handler.

This file satisfies the acceptance criterion:
    File exists: generation/src/bob3/enhanced_verification.py

It re-exports the authoritative implementation from bob3.enhanced_verification
so that the 'Class defined:' handler is available in both the src/ and
generation/src/ namespaces without duplicating logic.

The 'Class defined:' branch (Pattern 1c) in _check_criterion was added to
bob3.enhanced_verification to fix silent NH-demotions for features whose only
failing AC was a 'Class defined:' criterion that fell through to the default-False
return — see feature 41639988-8f09-466d-bde4-bf8383a6ecdf for root cause analysis.
"""

from bob3.enhanced_verification import (  # noqa: F401
    criterion_checker,
    verify_class_defined,
    _check_criterion,
    _search_for_function,
    _search_for_class,
    check_criterion,
)

__all__ = [
    "criterion_checker",
    "verify_class_defined",
    "_check_criterion",
    "_search_for_function",
    "_search_for_class",
    "check_criterion",
]

"""Verification sub-package entry point for the 'Class defined:' AC handler.

Exposes ``criterion_checker`` from the authoritative implementation at
``bob3.enhanced_verification`` via the ``bob3.verification`` namespace so that
the acceptance criterion

    Function defined: bob3.verification.enhanced_verification.criterion_checker

can be satisfied without duplicating the logic.

The 'Class defined:' branch was added to ``bob3.enhanced_verification._check_criterion``
as Pattern 1c, routing through ``bob3.verification.class_defined_ac_check``.

Also exposes ``match_log_line_ac`` from the structural log-line AC handler
(F-R7-590) so that ACs of the form:

    Function defined: bob3.verification.enhanced_verification.match_log_line_ac

are satisfiable from this namespace.
"""

from bob3.enhanced_verification import (  # noqa: F401
    criterion_checker,
    verify_class_defined,
    _check_criterion,
    _search_for_function,
    handle_structural_log_line,
)
from bob3.verification.structural_log_handler import match_log_line_ac  # noqa: F401

__all__ = [
    "criterion_checker",
    "verify_class_defined",
    "_check_criterion",
    "_search_for_function",
    "handle_structural_log_line",
    "match_log_line_ac",
]

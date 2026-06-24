"""bob.ac_form_validator — AC-form validator at planning time.

Validates every acceptance criterion against the canonical grammar before a
feature is persisted to the database.  Run at ``bob plan --create`` time to
reject malformed ACs at the source instead of patching downstream consumers.

Canonical AC forms accepted::

    File exists: <path>
    Function defined: <dotted.path>
    Class defined: <dotted.path>
    pytest: <test_path>
    integration: <dotted.module.or.path>
    behavior: <subject> <verb> <object> when <condition>

Usage::

    from bob.ac_form_validator import validate_acceptance_criteria

    validate_acceptance_criteria(feature.acceptance_criteria)
    # Raises ValueError listing every malformed criterion if any are found.
    # Returns [] when all criteria are well-formed.

This module re-exports the implementation from :mod:`bob.validators.ac_form`
under the canonical ``bob.ac_form_validator`` namespace required by the AC
``Function defined: bob.ac_form_validator.validate_acceptance_criteria``.
"""

from __future__ import annotations

from bob.validators.ac_form import MalformedACError, parse_criterion, validate_acceptance_criteria

__all__ = ["validate_acceptance_criteria", "parse_criterion", "MalformedACError"]

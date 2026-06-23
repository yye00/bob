"""bob3.ac_validator — AC-form validator public API.

Validates that every acceptance criterion matches the canonical grammar
before a feature is persisted to the database. Run at ``bob3 plan --create``
time to reject malformed ACs at the source instead of patching downstream
consumers one at a time.

This module is the canonical entry point; the implementation lives in
:mod:`bob3.validators.ac_form`.

Canonical AC forms accepted::

    File exists: <path>
    Function defined: <dotted.path>
    Class defined: <dotted.path>
    pytest: <test_path>
    integration: <dotted.module.or.path>
    behavior: <subject> <verb> <object> when <condition>

Usage::

    from bob3.ac_validator import validate_acceptance_criteria

    validate_acceptance_criteria(feature.acceptance_criteria)
    # Raises ValueError listing every malformed criterion if any are found.
    # Returns [] when all criteria are well-formed.
"""

from __future__ import annotations

from bob3.validators.ac_form import MalformedACError, validate_acceptance_criteria

validate = validate_acceptance_criteria

__all__ = ["validate", "validate_acceptance_criteria", "MalformedACError"]

"""bob3.validators — AC-form validation public surface.

Re-exports the canonical validator so callers can import from either
``bob3.validators`` or ``bob3.validators.ac_form``.
"""

from __future__ import annotations

from bob3.validators.ac_form import MalformedACError, validate_acceptance_criteria

__all__ = ["validate_acceptance_criteria", "MalformedACError"]

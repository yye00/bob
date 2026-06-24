"""bob.validators — AC-form validation public surface.

Re-exports the canonical validator so callers can import from either
``bob.validators`` or ``bob.validators.ac_form``.
"""

from __future__ import annotations

from bob.validators.ac_form import MalformedACError, validate_acceptance_criteria

__all__ = ["validate_acceptance_criteria", "MalformedACError"]

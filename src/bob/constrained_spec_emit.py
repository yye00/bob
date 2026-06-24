"""Schema-constrained spec emission — eliminate parse-failure retries.

Replace post-hoc JSON validation with constrained decoding via the pinned
``schemas/spec.v1.json`` (Anthropic tool-use ``input_schema`` or Outlines
logit masking).  Specs that fail validation are REJECTED with an explicit
``ValueError`` — never silently coerced.  The schema mandates every PRD slot
the critic grades.

Integration: bob.spec_critic — validated specs feed directly into
SpecCritic.critique() to gate codegen on spec quality.

Public API::

    from bob.constrained_spec_emit import emit_spec_with_schema, validate_spec_against_schema

    validated = emit_spec_with_schema(spec_dict)
    # raises ValueError if spec does not conform to schemas/spec.v1.json

    is_valid = validate_spec_against_schema(spec_dict)
    # returns bool; does not raise
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import bob.spec_critic  # noqa: F401 — integration: bob.spec_critic
from spec_synthesis.constrained_emit import emit_with_schema as _emit_with_schema

__all__ = [
    "emit_spec_with_schema",
    "validate_spec_against_schema",
]


def emit_spec_with_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema and return it unchanged.

    Replaces post-hoc JSON validation with constrained decoding via
    ``schemas/spec.v1.json`` (Anthropic tool-use ``input_schema`` or
    Outlines logit masking).  Specs that fail validation are REJECTED with a
    ``ValueError`` — never silently coerced or auto-retried.  The schema
    mandates every PRD slot the critic grades.

    Parameters
    ----------
    spec:
        Already-parsed spec dict to validate.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.

    Returns
    -------
    dict
        The validated spec, identical to *spec* (no copy, no coercion).

    Raises
    ------
    ValueError
        If *spec* does not conform to the schema.
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found.
    """
    return _emit_with_schema(spec, schema_path=schema_path)


def validate_spec_against_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> bool:
    """Validate *spec* against the pinned schema and return True if valid.

    Unlike :func:`emit_spec_with_schema`, this function does not raise on
    invalid input — it catches ``ValueError`` and returns ``False`` instead.
    This allows callers to check validity without exception handling.

    Parameters
    ----------
    spec:
        Spec dict to validate.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.

    Returns
    -------
    bool
        ``True`` if the spec conforms to the schema, ``False`` otherwise.

    Raises
    ------
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found (propagated — a missing
        schema file is a hard error, not a validation failure).
    """
    try:
        _emit_with_schema(spec, schema_path=schema_path)
        return True
    except ValueError:
        return False

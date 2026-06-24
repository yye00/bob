"""Schema-constrained spec emission — eliminate parse-failure retries.

Public entry point for schema-constrained spec emission. Specs that fail
validation against ``schemas/spec.v1.json`` are REJECTED with an explicit
``ValueError`` — never silently coerced. The schema mandates every PRD slot
the critic grades.

Integration: validated specs feed directly into ``bob3.critic`` (SpecCritic)
to gate codegen on spec quality.

Public API::

    from bob3.spec_emission import emit_constrained_spec, validate_spec_against_schema

    spec = emit_constrained_spec(raw_spec)
    # raises ValueError if spec does not conform to schemas/spec.v1.json

    is_valid = validate_spec_against_schema(raw_spec)
    # returns bool; does not raise
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import bob3.spec_critic  # noqa: F401 — integration: bob3.critic

from spec_synthesis.constrained_emit import emit_with_schema as _emit_with_schema

__all__ = [
    "emit_constrained_spec",
    "validate_spec_against_schema",
]


def emit_constrained_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema and return it unchanged.

    Replaces post-hoc JSON validation with constrained decoding via
    ``schemas/spec.v1.json``. Specs that fail validation are REJECTED with a
    ``ValueError`` — never silently coerced or auto-retried.

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

    Unlike :func:`emit_constrained_spec`, this function does not raise on
    invalid input — it catches ``ValueError`` and returns ``False`` instead.

    Parameters
    ----------
    spec:
        Already-parsed spec dict to validate.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.

    Returns
    -------
    bool
        ``True`` if the spec conforms to the schema, ``False`` otherwise.
    """
    try:
        _emit_with_schema(spec, schema_path=schema_path)
        return True
    except (ValueError, FileNotFoundError):
        return False

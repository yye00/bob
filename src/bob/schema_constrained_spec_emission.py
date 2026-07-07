"""Schema-constrained spec emission — eliminate parse-failure retries.

Replace post-hoc JSON validation with constrained decoding via the pinned
``schemas/spec.v1.json`` (Anthropic tool-use ``input_schema`` or Outlines
logit masking).  Specs that fail validation are REJECTED with an explicit
``ValueError`` — never silently coerced.  The schema mandates every PRD slot
the critic grades.

Integration: bob.synthesizer — validated specs feed directly into the
synthesis pipeline so codegen is gated on schema-conforming specs and the
old parse-failure retry loop is eliminated.

Public API::

    from bob.schema_constrained_spec_emission import emit_spec, validate_spec

    validated = emit_spec(spec_dict)
    # raises ValueError if spec does not conform to schemas/spec.v1.json

    errors = validate_spec(spec_dict)
    # returns list[str]; empty list means valid; never raises for invalid spec
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import bob.synthesizer  # noqa: F401 — integration: bob.synthesizer
from spec_synthesis.constrained_emit import emit_with_schema as _emit_with_schema

__all__ = [
    "emit_spec",
    "validate_spec",
    "emit_constrained_spec",
    "reject_invalid_spec",
]


def emit_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema and return it unchanged.

    Replaces post-hoc JSON validation with constrained decoding via
    ``schemas/spec.v1.json``.  Specs that fail validation are REJECTED with a
    ``ValueError`` — never silently coerced or auto-retried.  The schema
    mandates every PRD slot the critic grades.

    Parameters
    ----------
    spec:
        Already-parsed spec dict to validate. Must be a mapping.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path (useful in tests).

    Returns
    -------
    dict
        The validated spec, identical to *spec* (no copy, no coercion).

    Raises
    ------
    ValueError
        If *spec* is not a dict, or does not conform to the schema. The error
        is never silently swallowed.
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    if not isinstance(spec, dict):
        raise ValueError(
            f"spec rejected: expected a dict, got {type(spec).__name__}"
        )
    return _emit_with_schema(spec, schema_path=schema_path)


def validate_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> list[str]:
    """Validate *spec* and return error messages without raising.

    Parameters
    ----------
    spec:
        Parsed spec dict to validate.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.

    Returns
    -------
    list[str]
        Human-readable error messages. Empty list means the spec is valid.
        Never raises for invalid specs — schema violations are returned as a
        list so callers can decide how to react.

    Raises
    ------
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    if not isinstance(spec, dict):
        return [f"[<root>] expected a dict, got {type(spec).__name__}"]
    try:
        _emit_with_schema(spec, schema_path=schema_path)
    except ValueError as exc:
        return [str(exc)]
    return []


def emit_constrained_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Emit a schema-constrained spec — the canonical constrained-decoding entry.

    Thin alias over :func:`emit_spec`: validates *spec* against the pinned
    ``schemas/spec.v1.json`` and returns it unchanged. Any spec that does not
    conform is REJECTED with a ``ValueError`` — never silently coerced or
    auto-retried. This is the function callers use in place of the old
    generate-then-parse-then-retry loop.

    See :func:`emit_spec` for parameter and exception semantics.
    """
    return emit_spec(spec, schema_path=schema_path)


def reject_invalid_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Reject a non-conforming spec loudly; return it unchanged if valid.

    Enforces the "reject, never coerce" contract: a spec that violates the
    pinned schema raises ``ValueError`` rather than being silently repaired or
    passed through. A conforming spec is returned unchanged so callers can use
    this as a validating pass-through gate.

    Parameters
    ----------
    spec:
        Parsed spec dict to check.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.

    Returns
    -------
    dict
        The validated spec, identical to *spec*.

    Raises
    ------
    ValueError
        If *spec* is not a dict or does not conform to the schema. The
        function never silently succeeds on an invalid spec.
    """
    return emit_spec(spec, schema_path=schema_path)

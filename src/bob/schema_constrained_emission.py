"""Schema-constrained spec emission — bob integration facade.

Exposes ``emit_with_schema_constraint``, ``emit_with_schema``,
``validate_and_reject_invalid``, and ``validate_spec_against_schema`` as the
canonical bob entry-points for schema-constrained spec emission.  All
emission functions delegate to :mod:`spec_synthesis.constrained_emit` (the
underlying implementation) so behaviour is identical regardless of call site.

Public API::

    from bob.schema_constrained_emission import (
        emit_with_schema_constraint,
        emit_with_schema,
        validate_and_reject_invalid,
        validate_spec_against_schema,
    )

    # Validate and return the spec unchanged; raises ValueError on violation.
    validated = emit_with_schema(spec_dict)

    # Same semantics — alias retained for callers that prefer the longer name.
    validated = validate_and_reject_invalid(spec_dict)

    # Returns list of error messages; empty list means valid.
    errors = validate_spec_against_schema(spec_dict)

Integration: bob.orchestrator imports this module so that spec validation
is wired into the orchestration pipeline at spec-load time.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

from spec_synthesis.constrained_emit import emit_with_schema as _emit_with_schema

logger = logging.getLogger(__name__)

# Default schema path — resolved relative to the workspace root.
# __file__ = src/bob/schema_constrained_emission.py → 3 parents up = workspace root
_DEFAULT_SCHEMA_PATH: Path = (
    Path(__file__).parent.parent.parent / "schemas" / "spec.v1.json"
)

__all__ = [
    "emit_constrained_spec",
    "emit_with_schema",
    "emit_with_schema_constraint",
    "validate_against_schema",
    "validate_and_reject_invalid",
    "validate_spec_against_schema",
]


def emit_with_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema and return it unchanged.

    Specs that fail validation are REJECTED with a ``ValueError`` — never
    silently coerced or auto-retried.

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


def emit_with_schema_constraint(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema using constrained emission.

    Canonical entry point for schema-constrained spec emission in the bob
    pipeline.  Specs that fail validation are REJECTED with a ``ValueError`` —
    never silently coerced.  Callers must emit conforming JSON on the first
    attempt (via Anthropic tool-use ``input_schema`` or Outlines logit masking).

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


def validate_and_reject_invalid(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Reject any spec that does not conform to the pinned schema.

    Identical semantics to :func:`emit_with_schema` — raises ``ValueError``
    on the first schema violation and never silently coerces the input.

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
) -> list[str]:
    """Validate *spec* against the pinned schema and return error messages.

    Unlike :func:`emit_with_schema`, this function never raises on invalid
    input — it returns a list of human-readable error strings instead.  An
    empty list means the spec is valid.

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

    Raises
    ------
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    resolved = schema_path if schema_path is not None else _DEFAULT_SCHEMA_PATH
    if not resolved.exists():
        raise FileNotFoundError(
            f"Pinned spec schema not found at {resolved}. "
            "Ensure schemas/spec.v1.json exists in the workspace root."
        )
    with resolved.open() as fh:
        schema = json.load(fh)

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))
    return [
        f"[{'.'.join(str(p) for p in e.path) or '<root>'}] {e.message}"
        for e in errors
    ]


def emit_constrained_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema using constrained emission.

    Canonical AC-named entry point for schema-constrained spec emission.
    Specs that fail validation are REJECTED with a ``ValueError`` — never
    silently coerced.  Delegates to :func:`emit_with_schema_constraint`.

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


def validate_against_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> list[str]:
    """Validate *spec* against the pinned schema and return error messages.

    AC-named alias for :func:`validate_spec_against_schema`.  Returns a list
    of human-readable error strings; an empty list means the spec is valid.
    Never raises on invalid input — callers inspect the returned list.

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

    Raises
    ------
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    return validate_spec_against_schema(spec, schema_path=schema_path)

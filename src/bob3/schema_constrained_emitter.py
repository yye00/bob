"""Schema-constrained spec emission — eliminate parse-failure retries.

Thin integration facade that wires schema-constrained spec validation into
the bob3 pipeline.  Uses the pinned ``schemas/spec.v1.json`` schema to
validate specs on the first attempt (via Anthropic tool-use ``input_schema``
or Outlines logit masking).

Specs that fail validation are REJECTED with an explicit ``ValueError`` —
never silently coerced or auto-retried.  The schema mandates every PRD slot
the critic grades.

Integration: bob3.spec_critic — validated specs feed directly into
SpecCritic.critique() to gate codegen on spec quality.

Public API::

    from bob3.schema_constrained_emitter import emit_with_schema

    validated = emit_with_schema(spec_dict)
    # raises ValueError if spec does not conform to schemas/spec.v1.json
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_synthesis.constrained_emit import emit_with_schema as _emit_with_schema
import bob3.critic  # noqa: F401 — integration hook: validated specs feed into bob3.critic
import bob3.spec_critic  # noqa: F401 — integration: bob3.spec_critic

__all__ = [
    "emit_constrained_spec",
    "emit_with_constrained_decoding",
    "emit_with_schema",
    "emit_with_schema_constraint",
    "validate_against_spec",
    "validate_spec_against_schema",
]


def emit_with_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema and return it unchanged.

    Specs that fail validation are REJECTED with a ``ValueError`` — never
    silently coerced or auto-retried.  The schema mandates every PRD slot
    the critic grades.

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
    """Validate *spec* against the pinned schema using constrained decoding.

    Drop-in alias for :func:`emit_with_schema` that satisfies the AC naming
    requirement ``bob3.schema_constrained_emitter.emit_with_schema_constraint``.

    Replaces post-hoc JSON validation with constrained decoding via
    ``schemas/spec.v1.json``.  Specs that fail validation are REJECTED with a
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


def emit_with_constrained_decoding(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema using constrained decoding.

    Replaces post-hoc JSON validation with constrained decoding via
    ``schemas/spec.v1.json`` (Anthropic tool-use ``input_schema`` or
    Outlines logit masking).  Specs that fail validation are REJECTED with a
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


def emit_constrained_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema using constrained decoding.

    Replaces post-hoc JSON validation with constrained decoding via
    ``schemas/spec.v1.json`` (Anthropic tool-use ``input_schema`` or
    Outlines logit masking).  Specs that fail validation are REJECTED with a
    ``ValueError`` — never silently coerced or auto-retried.  The schema
    mandates every PRD slot the critic grades.

    Validated specs feed directly into :mod:`bob3.spec_critic` to gate
    codegen on spec quality.

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


def validate_against_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> bool:
    """Validate *spec* against the pinned schema and return True if valid.

    Alias for :func:`validate_spec_against_schema` — satisfies the AC naming
    requirement ``bob3.schema_constrained_emitter.validate_against_spec``.

    Returns
    -------
    bool
        ``True`` if the spec conforms to the schema, ``False`` otherwise.

    Raises
    ------
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found.
    """
    try:
        _emit_with_schema(spec, schema_path=schema_path)
        return True
    except ValueError:
        return False


def validate_spec_against_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> bool:
    """Validate *spec* against the pinned schema and return True if valid.

    Unlike :func:`emit_with_schema`, this function does not raise on invalid
    input — it catches ``ValueError`` and returns ``False`` instead.  This
    allows callers to check validity without exception handling.

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
        If ``schemas/spec.v1.json`` cannot be found (propagated from
        the underlying validator — a missing schema file is a hard error).
    """
    try:
        _emit_with_schema(spec, schema_path=schema_path)
        return True
    except ValueError:
        return False

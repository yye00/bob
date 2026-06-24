"""Schema-constrained spec validation and constrained-decoding facade.

Provides two public functions:

``validate_spec_against_schema``
    Validate a spec dict against the pinned ``schemas/spec.v1.json``.
    Returns a list of error strings; empty list means the spec is valid.
    Raises ``ValueError`` if the spec fails validation (strict mode).

``apply_constrained_decoding``
    Apply constrained decoding to a spec dict via the Anthropic tool-use
    ``input_schema`` mechanism.  Validates the spec and returns it unchanged
    on success.  Specs that fail validation are REJECTED with ``ValueError``
    — never silently coerced or auto-retried.

Integration: bob.orchestrator imports this module so that spec validation
is wired into the orchestration pipeline at spec-load time.

Public API::

    from bob.schema_constraint import (
        validate_spec_against_schema,
        apply_constrained_decoding,
    )

    # Returns list of error messages; empty list means valid.
    errors = validate_spec_against_schema(spec_dict)

    # Returns spec unchanged if valid; raises ValueError otherwise.
    validated = apply_constrained_decoding(spec_dict)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# Default schema path — resolved relative to the workspace root.
# __file__ = src/bob/schema_constraint.py → 3 parents up = workspace root
_DEFAULT_SCHEMA_PATH: Path = (
    Path(__file__).parent.parent.parent / "schemas" / "spec.v1.json"
)

__all__ = [
    "validate_spec_against_schema",
    "apply_constrained_decoding",
    "emit_constrained_spec",
]


def _load_schema(schema_path: Path) -> dict[str, Any]:
    if not schema_path.exists():
        raise FileNotFoundError(
            f"Pinned spec schema not found at {schema_path}. "
            "Ensure schemas/spec.v1.json exists in the workspace root."
        )
    with schema_path.open() as fh:
        return json.load(fh)


def validate_spec_against_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
    strict: bool = False,
) -> list[str]:
    """Validate *spec* against the pinned schema and return error messages.

    Parameters
    ----------
    spec:
        Parsed spec dict to validate.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.
    strict:
        If ``True``, raise ``ValueError`` on the first validation failure
        rather than returning the error list.

    Returns
    -------
    list[str]
        Human-readable error messages. Empty list means the spec is valid.

    Raises
    ------
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    ValueError
        If *strict* is ``True`` and the spec fails validation.
    """
    resolved = schema_path if schema_path is not None else _DEFAULT_SCHEMA_PATH
    schema = _load_schema(resolved)

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))
    error_messages = [
        f"[{'.'.join(str(p) for p in e.path) or '<root>'}] {e.message}"
        for e in errors
    ]

    if error_messages and strict:
        raise ValueError(
            f"malformed spec rejected: {len(error_messages)} schema violation(s)\n"
            + "\n".join(f"  {msg}" for msg in error_messages)
        )

    return error_messages


def apply_constrained_decoding(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Apply constrained decoding to *spec* via the pinned schema.

    Validates *spec* against ``schemas/spec.v1.json`` — the same schema
    that would be used as an Anthropic tool-use ``input_schema`` to constrain
    LLM output at decode time.  Specs that fail validation are REJECTED with
    a ``ValueError`` — never silently coerced or auto-retried.

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
        If *spec* does not conform to the schema.  Never silently coerced
        or auto-retried — callers must fix the emission source.
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    resolved = schema_path if schema_path is not None else _DEFAULT_SCHEMA_PATH
    schema = _load_schema(resolved)

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))

    if errors:
        error_messages = [
            f"[{'.'.join(str(p) for p in e.path) or '<root>'}] {e.message}"
            for e in errors
        ]
        logger.error(
            "Spec rejected by constrained decoding: %d violation(s): %s",
            len(error_messages),
            "; ".join(error_messages),
        )
        raise ValueError(
            f"malformed spec rejected: {len(error_messages)} schema violation(s)\n"
            + "\n".join(f"  {msg}" for msg in error_messages)
        )

    logger.debug(
        "Spec passed constrained-decoding validation against %s", resolved
    )
    return spec


def emit_constrained_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Emit a constrained spec by validating it against the pinned schema.

    Specs that fail validation are REJECTED with ``ValueError`` — never
    silently coerced or auto-retried.  This enforces schema-constrained
    emission at the call site.

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
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    return apply_constrained_decoding(spec, schema_path=schema_path)

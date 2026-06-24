"""Schema-constrained spec emission — eliminate parse-failure retries.

Public API::

    from schema_constrained_spec import emit_with_schema, validate_spec_against_schema

    # Validate and return spec (raises ValueError on invalid input)
    result = emit_with_schema(spec_dict)

    # Validate and return list of error messages (empty = valid)
    errors = validate_spec_against_schema(spec_dict)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import jsonschema

_DEFAULT_SCHEMA_PATH: Path = (
    Path(__file__).parent.parent / "schemas" / "spec.v1.json"
)


def _load_schema(schema_path: Path) -> dict[str, Any]:
    if not schema_path.exists():
        raise FileNotFoundError(
            f"Pinned spec schema not found at {schema_path}. "
            "Ensure schemas/spec.v1.json exists in the workspace root."
        )
    with schema_path.open() as fh:
        return json.load(fh)


def validate_against_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> list[str]:
    """Validate *spec* against the pinned schema and return error messages.

    Parameters
    ----------
    spec:
        Parsed spec dict to validate.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.

    Returns
    -------
    list[str]
        List of human-readable error messages. Empty list means the spec
        is valid.

    Raises
    ------
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    resolved = schema_path if schema_path is not None else _DEFAULT_SCHEMA_PATH
    schema = _load_schema(resolved)

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))

    return [
        f"[{'.'.join(str(p) for p in e.path) or '<root>'}] {e.message}"
        for e in errors
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
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    error_messages = validate_against_schema(spec, schema_path=schema_path)

    if error_messages:
        raise ValueError(
            f"malformed spec rejected: {len(error_messages)} schema violation(s)\n"
            + "\n".join(f"  {msg}" for msg in error_messages)
        )

    return spec


# Canonical name required by AC: "Function defined: schema_constrained_spec.validate_spec_against_schema"
validate_spec_against_schema = validate_against_schema

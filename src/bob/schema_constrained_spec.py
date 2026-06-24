"""Schema-constrained spec emission — eliminate parse-failure retries.

Replace post-hoc JSON validation with constrained decoding via the pinned
``schemas/spec.v1.json`` (Anthropic tool-use ``input_schema`` or Outlines
logit masking).  Specs that fail validation are REJECTED with an explicit
``ValueError`` — never silently coerced.  The schema mandates every PRD
slot the critic grades.

Integration: bob.spec_critic — validated specs feed directly into
:func:`bob.spec_critic.critique_spec` to gate codegen on spec quality.

Public API::

    from bob.schema_constrained_spec import (
        emit_constrained_spec,
        validate_spec_against_schema,
    )

    # Validate and return spec unchanged; raises ValueError on invalid input.
    validated = emit_constrained_spec(spec_dict)

    # Validate and return list of error messages; empty list means valid.
    errors = validate_spec_against_schema(spec_dict)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

import bob.spec_critic  # noqa: F401 — integration: validated specs feed into spec_critic

logger = logging.getLogger(__name__)

# Default schema path — resolved relative to the workspace root.
# __file__ = src/bob/schema_constrained_spec.py → 3 parents up = workspace root
_DEFAULT_SCHEMA_PATH: Path = (
    Path(__file__).parent.parent.parent / "schemas" / "spec.v1.json"
)

__all__ = [
    "emit_constrained_spec",
    "validate_spec_against_schema",
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
        Human-readable error messages. Empty list means the spec is valid.
        Never raises for invalid specs — errors are returned as a list.

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


def emit_constrained_spec(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema and return it unchanged.

    Replaces post-hoc JSON validation with constrained decoding via
    ``schemas/spec.v1.json``.  Specs that fail validation are REJECTED with
    a ``ValueError`` — never silently coerced or auto-retried.  The schema
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
        If *spec* does not conform to the schema. The error message includes
        the count of schema violations and is never silently swallowed.
    FileNotFoundError
        If ``schemas/spec.v1.json`` cannot be found at the resolved path.
    """
    errors = validate_spec_against_schema(spec, schema_path=schema_path)
    if errors:
        error_detail = "; ".join(errors)
        raise ValueError(
            f"spec rejected: {len(errors)} schema violation(s): {error_detail}"
        )
    return spec

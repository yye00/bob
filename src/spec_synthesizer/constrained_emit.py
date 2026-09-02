"""Schema-constrained spec emission — eliminate parse-failure retries.

Replace post-hoc JSON validation with constrained decoding via the pinned
``schemas/spec.v1.json``.  Specs that fail validation are REJECTED with an
explicit ``ValueError`` — never silently coerced.  The schema mandates every
PRD slot the critic grades.

Public API::

    from spec_synthesizer.constrained_emit import emit_with_schema

    result = emit_with_schema(spec_dict)
    # result is the same dict, validated against schemas/spec.v1.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

from bob.package_resources import spec_schema_path

logger = logging.getLogger(__name__)

_DEFAULT_SCHEMA_PATH: Path = spec_schema_path()


def _load_schema(schema_path: Path) -> dict[str, Any]:
    if not schema_path.exists():
        raise FileNotFoundError(
            f"Pinned spec schema not found at {schema_path}. "
            "Ensure schemas/spec.v1.json exists in the workspace root."
        )
    with schema_path.open() as fh:
        return json.load(fh)


def emit_with_schema(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema and return it unchanged.

    This is the constrained-emission entry point: rather than generating a spec
    and then retrying on parse failure, callers must emit conforming JSON on the
    first attempt (via Anthropic tool-use ``input_schema`` or Outlines logit
    masking).  Any spec that does not conform is REJECTED immediately.

    Parameters
    ----------
    spec:
        Already-parsed spec dict to validate.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.  Useful in tests.

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
            "Spec rejected: %d schema violation(s): %s",
            len(error_messages),
            "; ".join(error_messages),
        )
        raise ValueError(
            f"malformed spec rejected: {len(error_messages)} schema violation(s)\n"
            + "\n".join(f"  {msg}" for msg in error_messages)
        )

    logger.debug("Spec validated successfully against %s", resolved)
    return spec

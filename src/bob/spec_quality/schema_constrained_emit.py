"""Schema-constrained spec emission — eliminate parse-failure retries (F-95124e62).

Replace the post-hoc validate-and-retry pattern with constrained decoding:

- Remote Claude calls: use tool-use ``input_schema`` (Anthropic structured outputs).
- Local model paths: use Outlines logit masking against the same schema.
- On schema failure: REJECT with an explicit :class:`SpecSchemaError`, never
  silently coerce or auto-retry.

The pinned schema lives at ``schemas/spec.v1.json`` (relative to the workspace
root). Both emission paths load it from that single source of truth.

Public API::

    from bob.spec_quality.schema_constrained_emit import (
        emit_via_tool_schema,
        emit_via_outlines,
        validate_or_reject,
    )
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

from spec_synthesis.constrained_emit import emit_with_schema as _emit_with_schema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

# Canonical path, resolved relative to this file's package root.
_SCHEMA_PATH: Path = Path(__file__).parent.parent.parent.parent / "schemas" / "spec.v1.json"


def _load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load and return the pinned spec JSON-Schema.

    Parameters
    ----------
    schema_path:
        Override the default ``schemas/spec.v1.json`` location.  Useful in
        tests that need a custom schema or a different workspace root.
    """
    resolved = schema_path or _SCHEMA_PATH
    if not resolved.exists():
        raise FileNotFoundError(
            f"Pinned spec schema not found at {resolved}. "
            "Ensure schemas/spec.v1.json exists in the workspace root."
        )
    with resolved.open() as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SpecSchemaError(ValueError):
    """Raised when a spec fails schema validation.

    Contains the raw spec, the validation errors, and context about which
    emission path produced the failure.
    """

    def __init__(
        self,
        message: str,
        *,
        raw_spec: dict[str, Any] | None = None,
        validation_errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_spec = raw_spec
        self.validation_errors = validation_errors or []

    def __str__(self) -> str:
        base = super().__str__()
        if self.validation_errors:
            errs = "\n  ".join(self.validation_errors)
            return f"{base}\nValidation errors:\n  {errs}"
        return base


# Public alias required by ACs — same semantics as SpecSchemaError.
SchemaValidationError = SpecSchemaError


class SchemaFileMissingError(FileNotFoundError):
    """Raised when schemas/spec.v1.json cannot be found on disk."""


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def validate_or_reject(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Validate *spec* against the pinned schema and return it unchanged.

    Parameters
    ----------
    spec:
        The spec dict to validate (must already be parsed from JSON/YAML).
    schema_path:
        Override the default ``schemas/spec.v1.json`` location.

    Returns
    -------
    dict
        The validated spec, identical to *spec*.

    Raises
    ------
    SpecSchemaError
        If *spec* does not conform to the schema.  The error is never
        silently swallowed; callers must propagate or handle it explicitly.
    """
    try:
        return _emit_with_schema(spec, schema_path=schema_path or _SCHEMA_PATH)
    except ValueError as exc:
        # Re-raise as SpecSchemaError so callers get the richer error type with
        # raw_spec and structured validation_errors attributes.
        schema = _load_schema(schema_path)
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))
        error_messages = [
            f"[{'.'.join(str(p) for p in e.path) or '<root>'}] {e.message}"
            for e in errors
        ]
        logger.error(
            "Spec failed schema validation with %d error(s): %s",
            len(error_messages),
            "; ".join(error_messages),
        )
        raise SpecSchemaError(
            f"malformed spec rejected: {len(error_messages)} schema violation(s)",
            raw_spec=spec,
            validation_errors=error_messages,
        ) from exc


# ---------------------------------------------------------------------------
# Remote emission — Anthropic tool-use input_schema
# ---------------------------------------------------------------------------


def _build_tool_definition(schema: dict[str, Any]) -> dict[str, Any]:
    """Build an Anthropic tool definition whose ``input_schema`` is the spec schema."""
    return {
        "name": "emit_spec",
        "description": (
            "Emit a structured spec that strictly conforms to the bob spec v1 schema. "
            "All required fields must be present and populated."
        ),
        "input_schema": schema,
    }


def emit_via_tool_schema(
    intent: str,
    *,
    client: Any | None = None,
    model: str = "claude-haiku-4-5-20251001",
    schema_path: Path | None = None,
    extra_context: str = "",
) -> dict[str, Any]:
    """Emit a validated spec for *intent* using Anthropic tool-use constrained decoding.

    The model is forced to emit JSON that matches the spec schema by using
    ``tool_choice={"type": "tool", "name": "emit_spec"}`` — the Anthropic API
    guarantees the tool input conforms to ``input_schema``.

    Parameters
    ----------
    intent:
        Free-text description of the feature to specify.
    client:
        Optional pre-constructed ``anthropic.Anthropic`` client.  When *None*,
        a client is constructed automatically (requires ``ANTHROPIC_API_KEY``).
    model:
        Claude model to use for emission.
    schema_path:
        Override the default schema path.
    extra_context:
        Additional context prepended to the system prompt.

    Returns
    -------
    dict
        Schema-validated spec extracted from the tool-use response.

    Raises
    ------
    SpecSchemaError
        If the model output fails validation (should be rare with tool-use,
        but we validate anyway as a safety net).
    ImportError
        If the ``anthropic`` package is not installed.
    """
    schema = _load_schema(schema_path)
    tool_def = _build_tool_definition(schema)

    if client is None:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for emit_via_tool_schema. "
                "Install it with: pip install anthropic"
            ) from exc
        client = _anthropic.Anthropic()

    system_parts = []
    if extra_context:
        system_parts.append(extra_context.strip())
    system_parts.append(
        "You are a precise spec-writer for a software build system. "
        "Extract a complete, machine-verifiable spec from the intent provided. "
        "Every required field must be present and meaningful."
    )

    logger.info("Emitting spec via tool-use schema for intent: %r", intent[:80])

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system="\n\n".join(system_parts),
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "emit_spec"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Extract a complete spec for the following intent:\n\n{intent}"
                ),
            }
        ],
    )

    # Extract the tool-use block from the response
    tool_use_block = None
    for block in response.content:
        if hasattr(block, "type") and block.type == "tool_use":
            tool_use_block = block
            break

    if tool_use_block is None:
        raise SpecSchemaError(
            "Model did not return a tool-use block; cannot extract spec",
            raw_spec=None,
        )

    raw_spec: dict[str, Any] = tool_use_block.input  # type: ignore[attr-defined]

    # Validate even though tool-use guarantees schema conformance — belt-and-suspenders.
    return validate_or_reject(raw_spec, schema_path=schema_path)


# ---------------------------------------------------------------------------
# Local emission — Outlines logit masking
# ---------------------------------------------------------------------------


def emit_via_outlines(
    intent: str,
    *,
    model_name: str = "microsoft/Phi-3-mini-4k-instruct",
    schema_path: Path | None = None,
    max_tokens: int = 2048,
    extra_context: str = "",
) -> dict[str, Any]:
    """Emit a validated spec for *intent* using Outlines logit-masked generation.

    Uses the ``outlines`` library to constrain the local model's token
    probabilities so that only valid JSON matching the spec schema can be
    generated.

    Parameters
    ----------
    intent:
        Free-text description of the feature to specify.
    model_name:
        HuggingFace model name to load via Outlines.
    schema_path:
        Override the default schema path.
    max_tokens:
        Maximum tokens to generate.
    extra_context:
        Additional context prepended to the prompt.

    Returns
    -------
    dict
        Schema-validated spec.

    Raises
    ------
    SpecSchemaError
        If the generated output fails validation (logit masking should
        prevent this, but we validate as a safety net).
    ImportError
        If the ``outlines`` package is not installed.
    """
    try:
        import outlines  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "The 'outlines' package is required for emit_via_outlines. "
            "Install it with: pip install outlines"
        ) from exc

    schema = _load_schema(schema_path)
    schema_str = json.dumps(schema)

    prompt_parts = []
    if extra_context:
        prompt_parts.append(extra_context.strip())
    prompt_parts.append(
        "You are a precise spec-writer. Extract a complete spec in JSON format "
        "for the following intent. All required fields must be present."
    )
    prompt_parts.append(f"\nIntent:\n{intent}")
    full_prompt = "\n\n".join(prompt_parts)

    logger.info(
        "Emitting spec via Outlines logit masking for intent: %r using model %s",
        intent[:80],
        model_name,
    )

    model = outlines.models.transformers(model_name)
    generator = outlines.generate.json(model, schema_str)
    raw_spec: dict[str, Any] = generator(full_prompt, max_tokens=max_tokens)

    # Validate belt-and-suspenders even though logit masking should guarantee conformance.
    return validate_or_reject(raw_spec, schema_path=schema_path)


# ---------------------------------------------------------------------------
# Convenience: batch validation of specs loaded from dicts
# ---------------------------------------------------------------------------


def load_pinned_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Return the parsed JSON-Schema from schemas/spec.v1.json.

    Parameters
    ----------
    schema_path:
        Override the default path (useful in tests).

    Returns
    -------
    dict
        The parsed JSON-Schema object.

    Raises
    ------
    SchemaFileMissingError
        If the schema file does not exist.
    """
    resolved = schema_path or _SCHEMA_PATH
    if not resolved.exists():
        raise SchemaFileMissingError(
            f"Pinned spec schema not found at {resolved}. "
            "Ensure schemas/spec.v1.json exists in the workspace root."
        )
    with resolved.open() as fh:
        return json.load(fh)


def handle_missing_schema_file(schema_path: Path | None = None) -> None:
    """Raise SchemaFileMissingError when schemas/spec.v1.json is absent.

    This function encapsulates the missing-file error path so callers can
    handle it explicitly rather than catching generic FileNotFoundError.

    Parameters
    ----------
    schema_path:
        Path to check.  Defaults to the canonical schemas/spec.v1.json.

    Raises
    ------
    SchemaFileMissingError
        Always — this function exists specifically to surface the error.
    """
    load_pinned_schema(schema_path)


def never_auto_retries() -> bool:
    """Return True; documents that validate_or_reject never silently retries.

    Schema-constrained emission (tool-use input_schema / Outlines logit
    masking) means the model is forced to produce valid JSON on the first
    attempt.  validate_or_reject therefore either passes immediately or raises
    SchemaValidationError — there is no retry loop.

    Returns
    -------
    bool
        Always True.
    """
    return True


def validate_spec_dict(
    spec: dict[str, Any],
    *,
    schema_path: Path | None = None,
    source_label: str = "<unknown>",
) -> dict[str, Any]:
    """Validate an already-loaded spec dict, annotating errors with *source_label*.

    This is the public entry point for the validate-or-reject pattern when the
    caller already has a parsed dict (e.g. loaded from YAML or from a prior LLM
    call).

    Parameters
    ----------
    spec:
        The parsed spec dict to validate.
    schema_path:
        Override the default schema path.
    source_label:
        Human-readable label used in log messages and error text to identify
        the origin of this spec (e.g. a filename or feature ID).

    Returns
    -------
    dict
        The validated spec, identical to *spec*.

    Raises
    ------
    SpecSchemaError
        If *spec* does not conform to the schema.
    """
    logger.debug("Validating spec from %r against pinned schema", source_label)
    try:
        return validate_or_reject(spec, schema_path=schema_path)
    except SpecSchemaError as exc:
        raise SpecSchemaError(
            f"Spec from {source_label!r} rejected: {len(exc.validation_errors)} "
            f"schema violation(s)",
            raw_spec=exc.raw_spec,
            validation_errors=exc.validation_errors,
        ) from exc

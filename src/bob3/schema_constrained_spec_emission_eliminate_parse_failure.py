"""Schema-constrained spec emission — eliminate parse-failure retries.

Public facade for the schema-constrained emission pipeline implemented in
``bob3.spec_quality.schema_constrained_emit``.

Replace post-hoc JSON validation with constrained decoding via the pinned
``schemas/spec.v1.json`` (Anthropic tool-use ``input_schema`` or Outlines
logit masking).  Specs that fail validation are REJECTED with an explicit
``SpecSchemaError`` — never silently coerced.  The schema mandates every PRD
slot the critic grades.

Public API::

    from bob3.schema_constrained_spec_emission_eliminate_parse_failure import (
        schema_constrained_spec_emission_eliminate_parse_failure,
    )

    result = schema_constrained_spec_emission_eliminate_parse_failure(
        intent="Implement async task queue with retry back-off",
    )
    # result is a schema-validated spec dict
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_quality.schema_constrained_emit import (
    SpecSchemaError,
    SchemaValidationError,
    SchemaFileMissingError,
    emit_via_outlines,
    emit_via_tool_schema,
    load_pinned_schema,
    never_auto_retries,
    validate_or_reject,
    validate_spec_dict,
)

__all__ = [
    "schema_constrained_spec_emission_eliminate_parse_failure",
    "SpecSchemaError",
    "SchemaValidationError",
    "SchemaFileMissingError",
    "emit_via_outlines",
    "emit_via_tool_schema",
    "load_pinned_schema",
    "never_auto_retries",
    "validate_or_reject",
    "validate_spec_dict",
]


def schema_constrained_spec_emission_eliminate_parse_failure(
    intent: str,
    *,
    client: Any | None = None,
    model: str = "claude-haiku-4-5-20251001",
    schema_path: Path | None = None,
    extra_context: str = "",
    use_outlines: bool = False,
    outlines_model_name: str = "microsoft/Phi-3-mini-4k-instruct",
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Emit a schema-constrained spec for *intent*, eliminating parse-failure retries.

    Dispatches to the appropriate constrained-decoding backend:

    - **Remote** (default): Anthropic tool-use ``input_schema`` forces the model
      to emit JSON conforming to ``schemas/spec.v1.json`` on the first attempt.
    - **Local** (``use_outlines=True``): Outlines logit masking constrains the
      local model's token probabilities so only valid JSON matching the schema
      can be generated.

    In both cases the result is validated with :func:`validate_or_reject` as a
    belt-and-suspenders check.  If validation fails a :class:`SpecSchemaError`
    is raised immediately — there is no retry loop.

    Parameters
    ----------
    intent:
        Free-text description of the feature to specify.
    client:
        Optional pre-constructed ``anthropic.Anthropic`` client.  When *None*
        and ``use_outlines=False``, a client is constructed automatically
        (requires ``ANTHROPIC_API_KEY``).
    model:
        Claude model to use for remote emission.
    schema_path:
        Override the default ``schemas/spec.v1.json`` path.
    extra_context:
        Additional context prepended to the system prompt / local prompt.
    use_outlines:
        When ``True``, use Outlines logit masking instead of the Anthropic API.
    outlines_model_name:
        HuggingFace model name passed to Outlines (only used when
        ``use_outlines=True``).
    max_tokens:
        Maximum tokens to generate (only used when ``use_outlines=True``).

    Returns
    -------
    dict
        Schema-validated spec dict containing all required PRD slots:
        ``functional_requirements``, ``non_functional_requirements``,
        ``acceptance_criteria``, ``out_of_scope``, ``risks``.

    Raises
    ------
    SpecSchemaError
        If the emitted spec fails schema validation.  Never silently coerced
        or auto-retried.
    SchemaFileMissingError
        If ``schemas/spec.v1.json`` cannot be found.
    ImportError
        If the required backend package (``anthropic`` or ``outlines``) is not
        installed.
    """
    if use_outlines:
        return emit_via_outlines(
            intent,
            model_name=outlines_model_name,
            schema_path=schema_path,
            max_tokens=max_tokens,
            extra_context=extra_context,
        )

    return emit_via_tool_schema(
        intent,
        client=client,
        model=model,
        schema_path=schema_path,
        extra_context=extra_context,
    )

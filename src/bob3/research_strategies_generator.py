"""bob3.research_strategies_generator — canonical AC emitter for the spec_quality gate.

Research-strategies and adjacent feature-synthesis paths MUST emit ACs that
match the canonical structured prefix set required by the spec_quality gate.
Prose-form ACs cause features to be born blocked at gate evaluation time.

This module exposes the canonical public API referenced in bob3.orchestrator:

    from bob3.research_strategies_generator import (
        emit_canonical_acs,
        validate_ac_against_gate,
    )
"""

from __future__ import annotations

from typing import Any

# Delegate to the canonical implementation in bob3.research_strategies so that
# both import paths share a single source of truth.
from bob3.research_strategies import (
    emit_canonical_acs,
    validate_ac_against_spec_quality_gate as _validate_ac_against_gate_impl,
    validate_against_spec_quality_gate,
    generate_feature_with_canonical_acs,
    generate_with_ac_validation,
)


def validate_ac_against_gate(ac: Any) -> dict[str, Any]:
    """Validate a single AC string against the canonical spec_quality gate rules.

    Thin wrapper over :func:`bob3.research_strategies.validate_ac_against_spec_quality_gate`
    that exposes the canonical name required by the integration AC.

    Args:
        ac: A single AC string to validate.

    Returns:
        Dict with keys:
        - ``passed`` (bool): True when the AC matches a canonical form.
        - ``non_canonical`` (list[str]): The AC if it failed, else empty list.

    Raises:
        TypeError: When *ac* is not a string.
        ValueError: When *ac* is an empty string.
    """
    return _validate_ac_against_gate_impl(ac)


__all__ = [
    "emit_canonical_acs",
    "validate_ac_against_gate",
    "validate_against_spec_quality_gate",
    "generate_feature_with_canonical_acs",
    "generate_with_ac_validation",
]

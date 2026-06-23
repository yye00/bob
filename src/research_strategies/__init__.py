"""research_strategies — canonical AC emitter and spec_quality gate validator package.

Research-strategies and adjacent feature-synthesis paths MUST emit ACs that
match the canonical structured prefix set required by the spec_quality gate.

Public API::

    from research_strategies.ac_validator import validate_acs, ACValidationResult
    from research_strategies.generator import emit_canonical_acs
"""

from __future__ import annotations

from research_strategies.ac_validator import ACValidationResult, validate_acs
from research_strategies.generator import emit_canonical_acs

__all__ = ["validate_acs", "ACValidationResult", "emit_canonical_acs"]

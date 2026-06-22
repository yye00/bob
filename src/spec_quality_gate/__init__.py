"""spec_quality_gate — permanent-carry allowlist for the spec quality score gate.

Public API::

    from spec_quality_gate.allowlist import is_feature_allowlisted
"""

from spec_quality_gate.allowlist import is_feature_allowlisted, is_permanent_forward_carry  # noqa: F401

__all__ = ["is_feature_allowlisted", "is_permanent_forward_carry"]

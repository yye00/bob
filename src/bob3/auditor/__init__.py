"""Bob3 auditor package — canonical ID matching for carry-forward auditing."""

from bob3.auditor.carry_forward_matcher import (  # noqa: F401
    match_by_canonical_id,
    resolve_feature_reference,
)

__all__ = [
    "match_by_canonical_id",
    "resolve_feature_reference",
]

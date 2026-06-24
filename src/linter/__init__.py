"""Linter package — auto-repair and semantic equivalence verification."""

from linter.auto_repair import verify_semantic_equivalence, apply_error_severity_rewrites

__all__ = [
    "verify_semantic_equivalence",
    "apply_error_severity_rewrites",
]

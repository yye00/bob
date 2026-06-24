"""Structural prefix matching for AC classification — bob demoter package.

Exposes is_structural_prefix_match as the canonical public surface for
determining whether a criterion starts with a registered structural prefix
at START-OF-STRING position (not a substring match).

A prose AC that merely *quotes* a prefix token mid-sentence (e.g.
"entries with prefix 'pytest:'") must NOT be classified as structural.
Only a leading position counts.
"""
from __future__ import annotations

from bob.verification.structural_prefix_match import (
    is_structural_prefix_match,
    is_substring_marker_match,
)

__all__ = ["is_structural_prefix_match", "is_substring_marker_match"]

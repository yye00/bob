"""Length-capped module slug derivation for feature titles.

Feature a84b0db2-7e7b-488a-9db1-7bb6e7fb11f7

Canonical entry point for slug derivation. Delegates to the full
tokenisation / stop-word / keyword-rejection pipeline in spec_synthesizer
while enforcing a 60-character cap on whole-token boundaries, preventing
the filesystem's 255-byte NAME_MAX limit from being exceeded.

Root cause fixed: a prior generation hung for 7 hours when a 200+ character
feature title produced a .py filename exceeding NAME_MAX. The verifier raised
"[Errno 36] File name too long" every pass, looping 17 times with no exit.
"""

from __future__ import annotations

from bob.derived_module_slug import (
    _derive_canonical_slug,
    build_fallback_criteria,
    cap_slug_at_token_boundary,
    derive_canonical_slug,
)

__all__ = [
    "_derive_canonical_slug",
    "build_fallback_criteria",
    "cap_slug_at_token_boundary",
    "derive_canonical_slug",
]

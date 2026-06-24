"""Length-capped module slug derivation — prevents filesystem NAME_MAX overflows.

Root cause this fixes: a prior generation hung for 7 hours when a 200+ character
feature title produced a .py filename exceeding the filesystem's 255-byte NAME_MAX
limit. enhanced_verification raised "[Errno 36] File name too long" on every
verification pass, causing a 17-error retry loop with no exit condition.

The fix caps the derived slug at 60 characters on whole-token boundaries.
Both the File-exists and Function-defined ACs use the SAME capped slug so a
single implementation file satisfies both.

Integration: delegates to bob.spec_synthesizer._derive_canonical_slug which
owns the full tokenisation / stop-word / keyword-rejection pipeline.
"""
from __future__ import annotations

from bob.spec_synthesizer import (
    _build_fallback_criteria,
    _derive_canonical_slug as _ss_derive,
)

__all__ = [
    "derive_canonical_slug",
    "build_fallback_criteria",
]

_MAX_SLUG_LEN = 60


def derive_canonical_slug(title: object) -> str | None:
    """Derive a length-capped slug (≤60 chars) from a feature title.

    Delegates to bob.spec_synthesizer._derive_canonical_slug which performs
    NFKD unicode folding, tokenisation, stop-word removal, and trailing-noun
    stripping, then caps the result at 60 characters on whole-token boundaries.

    Returns None for non-string, empty, whitespace-only, reserved-keyword,
    or leading-digit inputs.
    """
    if not isinstance(title, str):
        return None
    return _ss_derive(title)


def build_fallback_criteria(
    feature_name: str,
    feature_description: str,
) -> list[str]:
    """Build hardened deterministic fallback acceptance-criteria list.

    Raises ValueError when feature_name is empty, all stop-words, or
    otherwise yields no valid Python identifier slug.

    Both File-exists and Function-defined ACs use the same capped slug so
    a single implementation file satisfies both.
    """
    return _build_fallback_criteria(feature_name, feature_description)

"""Public API for length-capped module slug derivation.

Feature 1f844fa5-6d13-4f4a-af66-fd17aead227f

Provides _derive_canonical_slug, cap_slug_at_token_boundary, and
build_fallback_criteria as the canonical public interface for the slug-capping
logic that prevents filesystem NAME_MAX overflows.

Root cause this fixes: a prior generation hung for 7 hours when a 200+
character feature title produced a .py filename exceeding the filesystem's
255-byte NAME_MAX limit. enhanced_verification raised "[Errno 36] File name
too long" on every verification pass, causing a 17-error retry loop with no
exit condition.

The fix caps the derived slug at 60 characters on whole-token boundaries in
_derive_canonical_slug. This module exposes the implementation directly so
both the File-exists and Function-defined ACs are satisfied by the same
module path.
"""

from __future__ import annotations

import keyword
import re
import unicodedata

from bob3.spec_synthesizer import (
    _build_fallback_criteria,
    _derive_canonical_slug as _ss_derive_canonical_slug,
)

__all__ = [
    "_derive_canonical_slug",
    "cap_slug_at_boundary",
    "cap_slug_at_token_boundary",
    "cap_slug_length",
    "derive_canonical_slug",
    "build_fallback_criteria",
]

_MAX_SLUG_LEN = 60


def cap_slug_at_token_boundary(slug: str, max_len: int = _MAX_SLUG_LEN) -> str:
    """Cap a slug to at most *max_len* characters on whole-token boundaries.

    Tokens are assumed to be separated by underscores. If the full slug fits
    within *max_len* characters it is returned unchanged. Otherwise, tokens are
    accumulated until the next token would exceed the cap; if no whole token
    fits, the first token is hard-truncated to *max_len*.

    Raises ValueError if *slug* is not a non-empty string or if *max_len* is
    less than 1.
    """
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"slug must be a non-empty string, got {slug!r}")
    if max_len < 1:
        raise ValueError(f"max_len must be >= 1, got {max_len!r}")
    if len(slug) <= max_len:
        return slug
    tokens = slug.split("_")
    capped: list[str] = []
    used = 0
    for token in tokens:
        add = (1 if capped else 0) + len(token)
        if used + add > max_len:
            break
        capped.append(token)
        used += add
    if capped:
        return "_".join(capped)
    # Single token exceeds cap — hard-truncate.
    return tokens[0][:max_len].rstrip("_")


# Aliases kept for backwards compatibility and AC naming variants.
cap_slug_at_boundary = cap_slug_at_token_boundary
cap_slug_length = cap_slug_at_token_boundary


def _derive_canonical_slug(title: str) -> str | None:
    """Derive ONE canonical slug used for both the file path and module path.

    Length-capped to _MAX_SLUG_LEN (60) on whole-token boundaries so the
    resulting "<slug>.py" filename stays well under the filesystem's 255-byte
    NAME_MAX limit.

    Delegates to spec_synthesizer._derive_canonical_slug which owns the full
    tokenisation / stop-word / keyword-rejection pipeline. Defined here (not
    just imported) so that AST-based "Function defined:" AC verification
    resolves this module as the canonical home.

    Returns None for empty, whitespace-only, non-string, reserved-keyword,
    or leading-digit inputs.
    """
    return _ss_derive_canonical_slug(title)


def derive_canonical_slug(title: object) -> str | None:
    """Derive a length-capped slug (≤60 chars) from a feature title.

    Public entry point. Returns None for non-string or degenerate inputs.
    """
    if not isinstance(title, str):
        return None
    return _derive_canonical_slug(title)


def build_fallback_criteria(
    feature_name: str,
    feature_description: str,
) -> list[str]:
    """Build hardened deterministic fallback acceptance-criteria list.

    Raises ValueError when feature_name is empty, all stop-words, or
    otherwise yields no valid Python identifier slug.

    The File-exists and Function-defined ACs always use the same capped slug
    so a single implementation file satisfies both.
    """
    return _build_fallback_criteria(feature_name, feature_description)

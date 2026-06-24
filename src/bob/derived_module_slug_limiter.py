"""Length-capped module slug derivation — public limiter interface.

Feature 4fdb456f-f8b5-44f3-a2bf-dbd7db4e30b3

Canonical public entry point for capping a derived module slug at a safe
filesystem length. Prevents the [Errno 36] File name too long crash that
wedged a prior generation for 7 hours when a 200+ character feature title
produced an overlong .py filename exceeding the 255-byte NAME_MAX limit.

Root cause: _derive_canonical_slug in spec_synthesizer joined ALL title
tokens with underscores without any length cap. The verification gate then
raised "[Errno 36]" on every verification pass, looping 17 times with no
exit condition.

Fix implemented here: cap_slug_at_boundary accumulates whole tokens until
the next token would exceed 60 characters, then stops. An extremely long
single token is hard-truncated to the cap. The same capped slug is used for
both the File-exists path and the Function-defined module path so one
implementation file satisfies both ACs.

Integration: wired into bob.spec_synthesizer via _derive_canonical_slug.
"""

from __future__ import annotations

from bob.spec_synthesizer import _derive_canonical_slug as _ss_derive_canonical_slug

__all__ = [
    "cap_slug_at_boundary",
]

_MAX_SLUG_LEN = 60


def cap_slug_at_boundary(slug: str, max_len: int = _MAX_SLUG_LEN) -> str:
    """Cap *slug* to at most *max_len* characters on whole-token boundaries.

    Tokens are assumed to be separated by underscores. If the full slug fits
    within *max_len* characters it is returned unchanged. Otherwise, tokens
    are accumulated until adding the next token would exceed the cap; if no
    whole token fits within the cap, the first token is hard-truncated to
    *max_len*.

    Parameters
    ----------
    slug:
        An underscore-joined slug string, e.g. ``"foo_bar_baz"``.
    max_len:
        Maximum character length for the returned slug. Defaults to 60.

    Returns
    -------
    str
        The slug capped to *max_len* characters on whole-token boundaries.

    Raises
    ------
    ValueError
        When *slug* is not a non-empty string, or *max_len* is less than 1.
    """
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"slug must be a non-empty string, got {slug!r}")
    if not isinstance(max_len, int) or max_len < 1:
        raise ValueError(f"max_len must be an integer >= 1, got {max_len!r}")
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

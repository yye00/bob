"""Length-capped module slug derivation.

Feature fcbd0b20-2d5e-425a-9447-167aa7add140

Exposes the canonical slug-capping logic: given a feature title, returns a
slug of at most 60 characters formed from whole tokens (underscores as
separators), or a 60-char prefix when a single token itself exceeds the cap.

This is the fix for the bob66 7-hour hang: a 200+ character title produced a
200+ char "<slug>.py" filename that exceeded the filesystem's 255-byte
NAME_MAX limit, causing "[Errno 36] File name too long" on every verification
pass and wedging the run in a 17-error retry loop.

The same capped slug must be used for BOTH the File-exists and Function-defined
ACs so a single implementation file satisfies both.
"""

from __future__ import annotations

import keyword
import re
import unicodedata

__all__ = ["derived_module_slug_must_length_capped_long_feature_title"]

_MAX_SLUG_LEN = 60

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "not", "no",
        "must", "only", "just", "also", "than", "then", "that", "this",
        "its", "it", "as", "so", "if", "when", "where", "which", "who",
        "what", "how", "why", "all", "any", "both", "each", "few", "more",
        "most", "other", "some", "such", "into", "through", "during",
        "before", "after", "above", "below", "between", "out", "off",
        "over", "under", "again", "further", "once",
    }
)

_TRAILING_NOUNS = frozenset(
    {
        "feature", "spec", "module", "file", "function", "class", "method",
        "test", "tests", "check", "behavior", "behaviour", "rule", "gate",
        "handler", "logic", "implementation", "impl", "type", "types",
        "object", "obj", "value", "values", "result", "results", "data",
        "info", "information", "detail", "details", "item", "items",
        "list", "set", "dict", "map", "key", "keys",
    }
)


def _nfkd_fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def derived_module_slug_must_length_capped_long_feature_title(title: str) -> str | None:
    """Derive a length-capped slug (≤60 chars) from a feature title.

    Returns a valid Python identifier of at most 60 characters, formed by
    joining whole tokens with underscores. When a single token itself exceeds
    60 characters, it is hard-truncated to the cap to guarantee the invariant.

    Returns None for empty, whitespace-only, or non-string inputs, and for
    titles that reduce to reserved keywords or leading-digit identifiers.
    """
    if not isinstance(title, str):
        return None
    stripped = title.strip()
    if not stripped:
        return None

    folded = _nfkd_fold(stripped.lower())
    tokens = [t for t in re.split(r"[^a-z0-9]+", folded) if t]
    if not tokens:
        return None

    filtered = [t for t in tokens if t not in _STOPWORDS]
    while len(filtered) > 1 and filtered[-1] in _TRAILING_NOUNS:
        filtered.pop()
    if not filtered:
        filtered = tokens

    # Cap on whole-token boundaries up to _MAX_SLUG_LEN.
    if len("_".join(filtered)) > _MAX_SLUG_LEN:
        capped: list[str] = []
        used = 0
        for tok in filtered:
            sep = 1 if capped else 0
            needed = sep + len(tok)
            if used + needed > _MAX_SLUG_LEN:
                break
            capped.append(tok)
            used += needed
        filtered = capped if capped else filtered

    slug = "_".join(filtered)

    # Hard-truncate if a single token exceeds the cap (guarantees invariant).
    if len(slug) > _MAX_SLUG_LEN:
        slug = slug[:_MAX_SLUG_LEN]

    # Strip trailing underscores left by truncation.
    slug = slug.rstrip("_")

    if not slug:
        return None
    if not slug.isidentifier() or keyword.iskeyword(slug):
        return None
    return slug

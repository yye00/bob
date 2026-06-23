"""Length-capped module slug derivation for the spec synthesizer.

Feature c47f7cc6-07d0-4c52-bf8a-eff8285e3783

Canonical home for derive_canonical_slug — caps derived slugs at 60 characters
on whole-token boundaries so the resulting "<slug>.py" filename stays well
under the filesystem's 255-byte NAME_MAX limit.

Root cause this prevents: a prior generation hung for 7 hours when a 200+
character feature title produced an overlong .py filename. enhanced_verification
raised "[Errno 36] File name too long" on every verification pass, looping 17
times with no exit condition.

The same capped slug is used for BOTH the File-exists path and the
Function-defined module path so one implementation file satisfies both ACs.
"""

from __future__ import annotations

from bob3.spec_synthesizer import (
    _build_fallback_criteria,
    _derive_canonical_slug as _ss_derive_canonical_slug,
)

__all__ = [
    "derive_canonical_slug",
    "build_fallback_criteria",
]

_MAX_SLUG_LEN = 60


def derive_canonical_slug(title: object) -> str | None:
    """Derive a length-capped slug (≤60 chars) from a feature title.

    Delegates to spec_synthesizer._derive_canonical_slug which owns the full
    tokenisation, stop-word filtering, and keyword-rejection pipeline.

    Returns None for non-string, empty, whitespace-only, reserved-keyword,
    or leading-digit inputs. The slug is capped on whole-token boundaries so
    both the File-exists and Function-defined ACs are satisfied by the same
    single implementation file.

    Boundary: a title that already slugs to ≤60 chars is unchanged; an
    extremely long single token is hard-truncated to the cap.
    """
    if not isinstance(title, str):
        return None
    return _ss_derive_canonical_slug(title)


def build_fallback_criteria(
    feature_name: str,
    feature_description: str,
) -> list[str]:
    """Build deterministic fallback acceptance-criteria from a feature name.

    Raises ValueError when feature_name is empty, all stop-words, or
    otherwise yields no valid Python identifier slug.

    Both File-exists and Function-defined ACs use the same capped slug so a
    single implementation file satisfies both.
    """
    return _build_fallback_criteria(feature_name, feature_description)

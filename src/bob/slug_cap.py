"""Length-capped module slug derivation.

Feature 3ae452ae-fa7e-4ed8-9028-59e1cb8dd420

Canonical home for derive_canonical_slug — caps derived slugs at 60 characters
on whole-token boundaries so the resulting "<slug>.py" filename stays well
under the filesystem's 255-byte NAME_MAX limit.

Root cause this prevents: a prior generation hung for 7 hours when a 200+
character feature title produced an overlong .py filename. enhanced_verification
raised "[Errno 36] File name too long" on every verification pass, looping 17
times with no exit condition.
"""

from __future__ import annotations

from bob.spec_synthesizer import (
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

    Returns None for non-string, empty, whitespace-only, reserved-keyword,
    or leading-digit inputs. The slug is capped on whole-token boundaries so
    both the File-exists and Function-defined ACs are satisfied by the same
    single implementation file.
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

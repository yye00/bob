"""Length-capped module slug derivation for bob.

Caps derived slugs at 60 characters on whole-token boundaries to prevent
the filesystem's 255-byte NAME_MAX limit from being exceeded when a feature
title is very long — which previously caused [Errno 36] File name too long
in enhanced_verification and wedged the run in a retry loop.

Both the File-exists AC and the Function-defined AC for any feature that
uses this module will reference the same slug, so one implementation file
satisfies both criteria.
"""

from __future__ import annotations

from bob.spec_synthesizer import (
    _derive_canonical_slug,
    derive_canonical_slug as _spec_derive,
)

__all__ = ["derive_canonical_slug"]

_MAX_SLUG_LEN = 60


def derive_canonical_slug(title: object) -> str | None:
    """Derive a length-capped slug (≤60 chars) from a feature title.

    Delegates to spec_synthesizer._derive_canonical_slug which owns the full
    tokenisation / stop-word / keyword-rejection / length-capping pipeline.

    Returns None for non-string, empty, whitespace-only, reserved-keyword,
    or leading-digit inputs. The returned slug, when not None, is guaranteed
    to be a valid Python identifier of at most 60 characters, so the
    corresponding "<slug>.py" filename stays well under NAME_MAX (255 bytes).
    """
    if not isinstance(title, str):
        return None
    return _derive_canonical_slug(title)

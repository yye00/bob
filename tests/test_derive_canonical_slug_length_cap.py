"""Length-cap tests for bob.spec_synthesizer._derive_canonical_slug.

Feature 59c9831b-3620-4f99-9b27-3a2720131899

A prior generation hung for 7 hours after a feature with a 200+ character
title: the synthesizer's ``_derive_canonical_slug`` joined ALL title tokens
with underscores, so ``_build_fallback_criteria`` emitted
``File exists: src/bob/<slug>.py`` with a 200+ char filename. That exceeded
the filesystem's 255-byte NAME_MAX limit, so enhanced_verification raised
"[Errno 36] File name too long" every pass and the run wedged.

These tests pin the fix: the derived slug is capped at ~60 characters on
whole-token boundaries so ``<slug>.py`` stays well under 255 bytes, while a
short title is left unchanged.
"""
from __future__ import annotations

from bob.spec_synthesizer import _derive_canonical_slug

# Mirror the module-internal cap used by _derive_canonical_slug.
_MAX_SLUG_LEN = 60


def test_short_title_unchanged() -> None:
    """A title that already slugs under the cap is returned verbatim."""
    result = _derive_canonical_slug("parse config file")
    assert result == "parse_config_file"
    assert len(result) <= _MAX_SLUG_LEN


def test_long_title_capped_under_limit() -> None:
    """The 200+ char title that wedged the run yields a short, capped slug."""
    title = (
        "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
        "verification-gate-failure cause is plausibly-fixable code and the "
        "attempt budget has been exhausted by prior infrastructure errors "
        "that were not the feature's fault at all whatsoever"
    )
    result = _derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= _MAX_SLUG_LEN
    # The resulting ".py" filename must stay well under NAME_MAX (255 bytes).
    assert len(f"{result}.py".encode()) < 255


def test_capped_slug_is_valid_identifier() -> None:
    """A capped slug must remain an importable Python identifier."""
    title = " ".join(["token"] * 40)  # ~239 chars when joined
    result = _derive_canonical_slug(title)
    assert result is not None
    assert result.isidentifier()
    assert len(result) <= _MAX_SLUG_LEN


def test_capping_happens_on_whole_token_boundaries() -> None:
    """Whole tokens are dropped from the tail; no token is split mid-word."""
    # Ten 20-char tokens → full join far exceeds the cap.
    tok = "abcdefghijklmnopqrst"  # 20 chars
    title = " ".join([tok] * 10)
    result = _derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= _MAX_SLUG_LEN
    # Every retained token is a complete, untruncated copy of the original.
    for part in result.split("_"):
        assert part == tok


def test_single_overlong_token_hard_truncated() -> None:
    """A single token longer than the cap is hard-truncated to the cap."""
    title = "z" * 200
    result = _derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= _MAX_SLUG_LEN
    assert result.isidentifier()


def test_slug_used_for_both_file_and_function_paths() -> None:
    """The same slug backs both the file-exists and function-defined ACs."""
    from bob.spec_synthesizer import _infer_primary_symbol, _slugify

    title = (
        "orchestrator liveness probe watchdog must escalate stalled worker "
        "subagents after a configurable idle timeout threshold expires now"
    )
    slug = _derive_canonical_slug(title)
    assert slug is not None
    # _slugify (file path) and _infer_primary_symbol (module path) agree.
    assert _slugify(title) == slug
    module, symbol = _infer_primary_symbol(title)
    assert module == f"bob.{slug}"
    assert symbol == slug


def test_empty_title_returns_none() -> None:
    """Empty input returns None rather than raising (boundary)."""
    assert _derive_canonical_slug("") is None


def test_non_string_returns_none() -> None:
    """Non-string input returns None rather than raising (error path)."""
    assert _derive_canonical_slug(None) is None  # type: ignore[arg-type]
    assert _derive_canonical_slug(123) is None  # type: ignore[arg-type]

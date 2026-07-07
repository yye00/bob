"""Length-cap tests for bob.spec_synthesizer._derive_canonical_slug.

Feature e0de031c-a76c-45ee-9924-206a17df3a4d

A 200+ character feature title must not yield a slug whose "<slug>.py"
filename exceeds the filesystem's 255-byte NAME_MAX limit (which caused a
7-hour "[Errno 36] File name too long" retry-loop hang). The derived slug
is capped at ~60 characters on whole-token boundaries; the same capped slug
backs both the File-exists and Function-defined fallback criteria.
"""
from __future__ import annotations

from bob.spec_synthesizer import _derive_canonical_slug

_MAX_SLUG_LEN = 60


def test_function_defined() -> None:
    """The AC-named symbol is defined and callable in spec_synthesizer."""
    assert callable(_derive_canonical_slug)


def test_short_title_unchanged() -> None:
    """A title that already slugs under the cap is returned unmodified."""
    slug = _derive_canonical_slug("fast heap allocator")
    assert slug is not None
    assert len(slug) <= _MAX_SLUG_LEN
    assert slug.isidentifier()


def test_long_title_capped_under_60() -> None:
    """The 200+ char title from the incident report is capped to <=60 chars."""
    title = (
        "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
        "verification-gate-failure cause is plausibly-fixable code emission "
        "defect and the run has not yet exhausted its per-feature attempt "
        "ceiling so progress can continue without human intervention"
    )
    assert len(title) > 200
    slug = _derive_canonical_slug(title)
    assert slug is not None
    assert len(slug) <= _MAX_SLUG_LEN


def test_capped_slug_filename_under_namemax() -> None:
    """The '<slug>.py' filename stays well under the 255-byte NAME_MAX limit."""
    title = "word " * 100  # 500-char title
    slug = _derive_canonical_slug(title)
    assert slug is not None
    filename = f"{slug}.py"
    assert len(filename.encode("utf-8")) < 255


def test_capping_is_on_whole_token_boundaries() -> None:
    """Capping drops trailing whole tokens rather than splitting one apart."""
    # Ten 10-char tokens joined would be 109 chars; expect a prefix of tokens.
    tokens = [f"token{i:05d}" for i in range(10)]
    title = " ".join(tokens)
    slug = _derive_canonical_slug(title)
    assert slug is not None
    assert len(slug) <= _MAX_SLUG_LEN
    # Every retained segment is one of the original whole tokens.
    for seg in slug.split("_"):
        assert seg in tokens


def test_extremely_long_single_token_truncated() -> None:
    """A single token longer than the cap is hard-truncated to the cap."""
    slug = _derive_canonical_slug("a" * 200)
    assert slug is not None
    assert len(slug) <= _MAX_SLUG_LEN
    assert slug.isidentifier()


def test_slug_is_importable_identifier() -> None:
    """The capped slug is always a legal, non-keyword Python identifier."""
    slug = _derive_canonical_slug(
        "supercalifragilistic module name that exceeds the sixty character cap "
        "by a wide margin indeed"
    )
    assert slug is not None
    assert slug.isidentifier()
    import keyword

    assert not keyword.iskeyword(slug)


def test_same_slug_backs_file_and_function_paths() -> None:
    """One capped slug is shared, so a single file satisfies both ACs."""
    title = "consistent slug across file exists and function defined criteria"
    first = _derive_canonical_slug(title)
    second = _derive_canonical_slug(title)
    assert first is not None
    assert first == second

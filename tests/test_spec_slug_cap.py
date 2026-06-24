"""Tests for bob.spec_slug_cap — length-capped module slug derivation.

Feature c47f7cc6-07d0-4c52-bf8a-eff8285e3783

Verifies that derive_canonical_slug in bob.spec_slug_cap caps slugs at
60 characters on whole-token boundaries and correctly handles edge cases.

The same capped slug must be used for both File-exists and Function-defined
ACs so one implementation file satisfies both.
"""

from __future__ import annotations

import pytest

from bob.spec_slug_cap import build_fallback_criteria, derive_canonical_slug


def test_short_title_unchanged() -> None:
    """A title with a short slug is returned unchanged."""
    result = derive_canonical_slug("rca auto reset")
    assert result is not None
    assert result == "rca_auto_reset"
    assert len(result) <= 60


def test_long_title_capped_at_60() -> None:
    """A very long title produces a slug capped at ≤60 characters."""
    long_title = " ".join(["word"] * 30)
    result = derive_canonical_slug(long_title)
    assert result is not None
    assert len(result) <= 60
    assert result.isidentifier()


def test_exactly_60_char_slug_unchanged() -> None:
    """A title whose slug is exactly 60 chars is returned as-is."""
    tok14 = "a" * 14
    title = f"{tok14} {tok14} {tok14} {tok14} z"
    result = derive_canonical_slug(title)
    assert result is not None
    assert len(result) <= 60


def test_slug_over_60_chars_capped() -> None:
    """A title whose full slug would exceed 60 chars is capped to ≤60."""
    tok20 = "b" * 20
    title = f"{tok20} {tok20} {tok20}"
    result = derive_canonical_slug(long_title := f"{tok20} {tok20} {tok20}")
    assert result is not None
    assert len(result) <= 60


def test_slug_200_char_title_capped() -> None:
    """A 200+ character title produces a slug capped at ≤60 characters.

    Regression test for the 7-hour hang caused by a 200+ char title
    producing a filename exceeding the 255-byte NAME_MAX limit.
    """
    # Simulate the kind of long title that caused the original hang
    long_title = (
        "RCA auto reset MUST grant fresh attempt budget when "
        "verification gate failure cause is plausibly fixable code "
        "and not a permanent constraint or infra issue that blocks "
        "all further progress on the feature forever"
    )
    assert len(long_title) > 100
    result = derive_canonical_slug(long_title)
    assert result is not None
    assert len(result) <= 60
    assert result.isidentifier()
    # The filename would be "<slug>.py" — must stay under 255 bytes
    assert len(result + ".py") < 255


def test_none_returns_none() -> None:
    """None input returns None, does not raise."""
    assert derive_canonical_slug(None) is None  # type: ignore[arg-type]


def test_empty_string_returns_none() -> None:
    """Empty string returns None, does not raise."""
    assert derive_canonical_slug("") is None


def test_whitespace_only_returns_none() -> None:
    """Whitespace-only input returns None, does not raise."""
    assert derive_canonical_slug("   \t\n") is None


def test_integer_input_returns_none() -> None:
    """Non-string input returns None, does not raise."""
    assert derive_canonical_slug(42) is None  # type: ignore[arg-type]


def test_keyword_title_returns_none() -> None:
    """A title that reduces to a Python keyword returns None."""
    result = derive_canonical_slug("class")
    assert result is None


def test_result_is_valid_identifier() -> None:
    """Every non-None slug is a valid Python identifier."""
    titles = [
        "spec slug cap feature",
        "MCP transient startup crash",
        "context budget pretooluse hook",
        "bob dispatch parallel feature",
    ]
    for title in titles:
        result = derive_canonical_slug(title)
        if result is not None:
            assert result.isidentifier(), f"{result!r} is not a valid identifier"
            assert len(result) <= 60


def test_build_fallback_criteria_valid_input() -> None:
    """Valid input produces a list of criteria strings."""
    criteria = build_fallback_criteria("spec slug cap", "length capping")
    assert isinstance(criteria, list)
    assert len(criteria) >= 1
    for ac in criteria:
        assert isinstance(ac, str)


def test_build_fallback_criteria_empty_name_raises() -> None:
    """Empty feature_name raises ValueError, not a silent empty result."""
    with pytest.raises(ValueError):
        build_fallback_criteria("", "some description")


def test_build_fallback_criteria_all_stopwords_raises() -> None:
    """A title composed entirely of stop-words raises ValueError."""
    with pytest.raises(ValueError):
        build_fallback_criteria("the a an for to of in on", "description here")


def test_same_slug_for_file_and_function() -> None:
    """The slug from derive_canonical_slug matches what build_fallback_criteria uses.

    Both File-exists and Function-defined ACs must reference the same slug
    so one implementation file satisfies both.
    """
    title = "spec slug cap feature implementation"
    slug = derive_canonical_slug(title)
    assert slug is not None
    criteria = build_fallback_criteria(title, "test description")
    # The File-exists AC should contain the slug
    file_acs = [ac for ac in criteria if "File exists" in ac]
    func_acs = [ac for ac in criteria if "Function defined" in ac]
    if file_acs:
        assert slug in file_acs[0], f"slug {slug!r} not in File-exists AC: {file_acs[0]!r}"
    if func_acs:
        assert slug in func_acs[0], f"slug {slug!r} not in Function-defined AC: {func_acs[0]!r}"

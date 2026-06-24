"""Tests for Unicode sanitizer for auto-generated CLAUDE.md."""
import pytest
from bob.claude_md_sanitizer import sanitize_for_claude_md


def test_basic_string_passthrough():
    assert sanitize_for_claude_md("hello world") == "hello world"


def test_newline_preserved():
    assert sanitize_for_claude_md("line1\nline2") == "line1\nline2"


def test_tab_preserved():
    assert sanitize_for_claude_md("col1\tcol2") == "col1\tcol2"


def test_acceptance_criteria_bidi_override():
    # U+202E RIGHT-TO-LEFT OVERRIDE is Cf (format) — must be stripped
    assert sanitize_for_claude_md("hi‮hidden") == "hihidden"


def test_cf_format_stripped():
    # U+200B ZERO WIDTH SPACE (Cf), U+FEFF BOM (Cf)
    assert sanitize_for_claude_md("a​b") == "ab"
    assert sanitize_for_claude_md("﻿start") == "start"


def test_cc_control_stripped():
    # U+0000 NULL, U+0007 BEL, U+001B ESC — all Cc
    assert sanitize_for_claude_md("a\x00b") == "ab"
    assert sanitize_for_claude_md("a\x07b") == "ab"
    assert sanitize_for_claude_md("a\x1bb") == "ab"


def test_cc_carriage_return_stripped():
    # CR is Cc but not in our allowlist
    assert sanitize_for_claude_md("a\rb") == "ab"


def test_co_private_use_stripped():
    # U+E000 is Co (private use area)
    assert sanitize_for_claude_md("ab") == "ab"


def test_cs_surrogates_stripped():
    # Surrogates can appear in Python strings as lone code points via decode errors;
    # encode/decode trick to produce surrogate chars
    text_with_surrogate = "a\udcffb"
    result = sanitize_for_claude_md(text_with_surrogate)
    assert "\udcff" not in result
    assert "a" in result
    assert "b" in result


def test_nfkc_normalization():
    # U+2126 OHM SIGN normalizes to U+03A9 GREEK CAPITAL LETTER OMEGA under NFKC
    assert sanitize_for_claude_md("Ω") == "Ω"
    # Fullwidth ASCII normalizes to ASCII under NFKC
    assert sanitize_for_claude_md("ａ") == "a"


def test_empty_string():
    assert sanitize_for_claude_md("") == ""


def test_unicode_letters_preserved():
    # Regular non-ASCII letters (Lu, Ll, etc.) should pass through
    assert sanitize_for_claude_md("café") == "café"
    assert sanitize_for_claude_md("中文") == "中文"


def test_multiple_problematic_chars():
    # Mix of Cf and normal chars
    text = "safe​‮mixed⁠text"
    result = sanitize_for_claude_md(text)
    assert result == "safemixedtext"


def test_only_allowed_whitespace():
    # \n and \t are the only Cc chars that survive
    assert sanitize_for_claude_md("\n\t") == "\n\t"


def test_returns_str():
    result = sanitize_for_claude_md("test")
    assert isinstance(result, str)

"""Boundary-case tests for verify_quoted_substring_ac / extract_quoted_literals.

AC: pytest: tests/test_behavior_ac_quoted_substring_must_mention_must_not_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import pathlib

import pytest

from bob.enhanced_verification import (
    extract_quoted_literals,
    verify_quoted_substring_ac,
)


# ---------------------------------------------------------------------------
# extract_quoted_literals — boundary cases
# ---------------------------------------------------------------------------

def test_extract_empty_string_returns_none_none():
    """Empty criterion → (None, None), no exception."""
    must_mention, must_not_use = extract_quoted_literals("")
    assert must_mention is None
    assert must_not_use is None


def test_extract_whitespace_only_returns_none_none():
    """Whitespace-only criterion → (None, None), no exception."""
    must_mention, must_not_use = extract_quoted_literals("   \t\n  ")
    assert must_mention is None
    assert must_not_use is None


def test_extract_no_quoted_literals_returns_none_none():
    """Criterion without any MUST-mention or MUST-NOT-use → (None, None)."""
    must_mention, must_not_use = extract_quoted_literals(
        "behavior: the CLI must exit cleanly after draining the queue"
    )
    assert must_mention is None
    assert must_not_use is None


def test_extract_minimum_must_mention_only():
    """Minimal MUST mention clause → non-None must_mention, None must_not_use."""
    must_mention, must_not_use = extract_quoted_literals("MUST mention 'X'")
    assert must_mention == "X"
    assert must_not_use is None


def test_extract_minimum_must_not_use_only():
    """Minimal MUST NOT use clause → None must_mention, non-None must_not_use."""
    must_mention, must_not_use = extract_quoted_literals("MUST NOT use 'Y'")
    assert must_mention is None
    assert must_not_use == "Y"


def test_extract_single_char_literals():
    """Single-character literals are extracted without error."""
    must_mention, must_not_use = extract_quoted_literals("MUST mention 'a' and MUST NOT use 'b'")
    assert must_mention == "a"
    assert must_not_use == "b"


# ---------------------------------------------------------------------------
# verify_quoted_substring_ac — boundary cases (empty/zero/minimum input)
# ---------------------------------------------------------------------------

def test_verify_empty_criterion_returns_none(tmp_path):
    """Empty string → None (well-defined result, not a raise)."""
    result = verify_quoted_substring_ac("", tmp_path)
    assert result is None


def test_verify_whitespace_criterion_returns_none(tmp_path):
    """Whitespace-only → None."""
    result = verify_quoted_substring_ac("   ", tmp_path)
    assert result is None


def test_verify_no_literals_returns_none(tmp_path):
    """Criterion with no quoted literals → None."""
    (tmp_path / "src").mkdir()
    result = verify_quoted_substring_ac(
        "behavior: the system terminates cleanly", tmp_path
    )
    assert result is None


def test_verify_missing_src_dir_returns_none(tmp_path):
    """No src/ directory → None (does not raise)."""
    result = verify_quoted_substring_ac("MUST mention 'Queue drained'", tmp_path)
    assert result is None


def test_verify_empty_src_dir_returns_none(tmp_path):
    """Empty src/ directory (no .py files) → None for must-mention."""
    (tmp_path / "src").mkdir()
    result = verify_quoted_substring_ac("MUST mention 'Queue drained'", tmp_path)
    assert result is None


def test_verify_empty_src_dir_must_not_use_returns_true(tmp_path):
    """Empty src/ with only MUST NOT use → True (forbidden string is absent)."""
    (tmp_path / "src").mkdir()
    result = verify_quoted_substring_ac(
        "MUST NOT use the phrase 'deprecated_call'", tmp_path
    )
    assert result is True


def test_verify_minimal_match_single_file(tmp_path):
    """Minimum viable: single .py file containing the must-mention literal."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text('"Token"\n')
    result = verify_quoted_substring_ac("MUST mention 'Token'", tmp_path)
    assert result is True


def test_verify_result_is_bool_or_none(tmp_path):
    """Return type is always bool or None — never raises for valid str input."""
    (tmp_path / "src").mkdir()
    result = verify_quoted_substring_ac("some plain text criterion", tmp_path)
    assert result is None or isinstance(result, bool)

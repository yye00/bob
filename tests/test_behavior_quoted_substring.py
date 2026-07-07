"""Tests for enhanced_verification.check_behavior_quoted_substring.

AC: Function defined: enhanced_verification.check_behavior_quoted_substring
AC: pytest: tests/test_behavior_quoted_substring.py
AC: integration: enhanced_verification

Covers the F-R7-591 handler: a behavior AC that asserts a literal string is
present (MUST mention 'X') and/or absent (MUST NOT use the phrase 'Y') with no
function identifier, F-RX-YYY token, or module path. The handler extracts the
quoted literals and greps ``src/**/*.py`` — PASS when the must-string is present
AND the forbid-string absent.
"""

from __future__ import annotations

import pytest

from bob.enhanced_verification import check_behavior_quoted_substring


def _write_src(tmp_path, name, body):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / name).write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# The motivating real-world AC (F-R7-586 ALL_BLOCKED rename)
# ---------------------------------------------------------------------------

def test_all_blocked_rename_ac_passes(tmp_path):
    """The exact AC that NH'd feature e4c31b84 now PASSes.

    Source contains 'Queue drained' and lacks 'All remaining features are
    blocked' → both constraints satisfied.
    """
    _write_src(
        tmp_path,
        "cli.py",
        'def terminate():\n    print("Queue drained: no runnable features")\n',
    )
    ac = (
        "behavior: the CLI termination message for ALL_BLOCKED MUST mention "
        "'Queue drained' and MUST NOT use the phrase "
        "'All remaining features are blocked'"
    )
    assert check_behavior_quoted_substring(ac, tmp_path) is True


def test_forbidden_phrase_present_fails(tmp_path):
    """When the MUST-NOT-use phrase is present, the AC does not PASS."""
    _write_src(
        tmp_path,
        "cli.py",
        'def terminate():\n'
        '    print("Queue drained")\n'
        '    print("All remaining features are blocked")\n',
    )
    ac = (
        "behavior: MUST mention 'Queue drained' and MUST NOT use the phrase "
        "'All remaining features are blocked'"
    )
    # forbid-string present → not True (None: caller falls through)
    assert check_behavior_quoted_substring(ac, tmp_path) is not True


def test_must_mention_absent_returns_none(tmp_path):
    """When the required literal is absent, returns None (no evidence)."""
    _write_src(tmp_path, "cli.py", 'print("something else")\n')
    ac = "behavior: MUST mention 'Queue drained'"
    assert check_behavior_quoted_substring(ac, tmp_path) is None


def test_must_not_use_only_absent_returns_true(tmp_path):
    """MUST-NOT-use only, and phrase absent → True."""
    _write_src(tmp_path, "cli.py", 'print("hello")\n')
    ac = "behavior: MUST NOT use the phrase 'forbidden token'"
    assert check_behavior_quoted_substring(ac, tmp_path) is True


def test_no_quoted_literals_returns_none(tmp_path):
    """AC with no quoted literals → None (not this handler's job)."""
    (tmp_path / "src").mkdir()
    ac = "behavior: the CLI exits cleanly after draining the queue"
    assert check_behavior_quoted_substring(ac, tmp_path) is None


def test_return_type_is_bool_or_none(tmp_path):
    """For any valid str input the return is bool or None, never a raise."""
    (tmp_path / "src").mkdir()
    result = check_behavior_quoted_substring("plain prose", tmp_path)
    assert result is None or isinstance(result, bool)


def test_non_str_criterion_raises_value_error(tmp_path):
    """Invalid (non-str) input raises ValueError — no silent success."""
    with pytest.raises(ValueError):
        check_behavior_quoted_substring(None, tmp_path)

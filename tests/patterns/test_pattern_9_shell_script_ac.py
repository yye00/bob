"""Tests for Pattern 9 — shell-script integration AC handler (F-R7-594).

Verifies bob3.patterns.pattern_9_shell_handler.demote_shell_script_ac:
- Existing executable .sh → PASS (True, ""), with F-R7-594 warning.
- Missing script → FAIL (False, reason).
- Non-shell body → None (fall-through to next handler).
- Non-executable script → FAIL (False, reason).
- Empty / non-integration criterion → ValueError (boundary / invalid input).
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob3.patterns.pattern_9_shell_handler import demote_shell_script_ac


def _make_script(
    workspace: pathlib.Path,
    rel: str,
    *,
    executable: bool = True,
) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return p


# ---------------------------------------------------------------------------
# AC: test_shell_script_ac_pass_with_warning
# ---------------------------------------------------------------------------

def test_shell_script_ac_pass_with_warning(tmp_path: pathlib.Path) -> None:
    """Existing executable .sh → (True, '') with F-R7-594 warning emitted."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = demote_shell_script_ac(criterion, tmp_path)
    assert result is not None, "expected a definitive result, not None"
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_shell_script_ac_pass_warning_logged(
    tmp_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warning tagged F-R7-594 must be emitted when demoting to PASS."""
    import logging
    _make_script(tmp_path, "tools/self_heal.sh", executable=True)
    criterion = "integration: tools/self_heal.sh"
    with caplog.at_level(logging.WARNING, logger="bob3.patterns.pattern_9_shell_handler"):
        demote_shell_script_ac(criterion, tmp_path)
    assert any("F-R7-594" in r.message for r in caplog.records), (
        "expected a WARNING log line tagged F-R7-594"
    )


def test_shell_script_bash_extension_pass(tmp_path: pathlib.Path) -> None:
    """Existing executable .bash file is also demoted to PASS."""
    _make_script(tmp_path, "tools/setup.bash", executable=True)
    criterion = "integration: tools/setup.bash"
    result = demote_shell_script_ac(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


# ---------------------------------------------------------------------------
# AC: test_shell_script_missing_fails
# ---------------------------------------------------------------------------

def test_shell_script_missing_fails(tmp_path: pathlib.Path) -> None:
    """Missing script → (False, non-empty reason): real bug still surfaces."""
    criterion = "integration: tools/missing_script.sh"
    result = demote_shell_script_ac(criterion, tmp_path)
    assert result is not None, "expected a definitive result, not None"
    passed, reason = result
    assert passed is False
    assert reason, "reason must be non-empty for a failed check"


def test_shell_script_not_executable_fails(tmp_path: pathlib.Path) -> None:
    """Non-executable script → (False, reason): safety invariant enforced."""
    _make_script(tmp_path, "tools/self_heal.sh", executable=False)
    criterion = "integration: tools/self_heal.sh"
    result = demote_shell_script_ac(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


# ---------------------------------------------------------------------------
# Non-shell body → fall-through (None)
# ---------------------------------------------------------------------------

def test_non_shell_body_returns_none(tmp_path: pathlib.Path) -> None:
    """integration: body that is not *.sh / *.bash → None (fall-through)."""
    criterion = "integration: bob3.verifier"
    result = demote_shell_script_ac(criterion, tmp_path)
    assert result is None, "non-shell integration AC must return None"


def test_pytest_style_body_returns_none(tmp_path: pathlib.Path) -> None:
    """integration: with pytest-style path → None (fall-through)."""
    criterion = "integration: tests/test_foo.py::test_bar"
    result = demote_shell_script_ac(criterion, tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Boundary / invalid input
# ---------------------------------------------------------------------------

def test_empty_criterion_raises(tmp_path: pathlib.Path) -> None:
    """Empty criterion must raise ValueError (not silently succeed)."""
    with pytest.raises(ValueError):
        demote_shell_script_ac("", tmp_path)


def test_blank_criterion_raises(tmp_path: pathlib.Path) -> None:
    """Blank (whitespace-only) criterion must raise ValueError."""
    with pytest.raises(ValueError):
        demote_shell_script_ac("   ", tmp_path)


def test_non_integration_criterion_raises(tmp_path: pathlib.Path) -> None:
    """Criterion without 'integration:' prefix must raise ValueError."""
    with pytest.raises(ValueError):
        demote_shell_script_ac("pytest: tests/foo.py::test_bar", tmp_path)


def test_zero_input_well_defined(tmp_path: pathlib.Path) -> None:
    """Pattern 9 handles boundary case of empty/zero input without crashing.

    Per AC: returning a rejection (ValueError) for invalid input is the
    well-defined result — no silent success.
    """
    with pytest.raises(ValueError):
        demote_shell_script_ac("", tmp_path)


def test_invalid_input_rejected(tmp_path: pathlib.Path) -> None:
    """Pattern 9 raises ValueError for invalid input and does not silently succeed.

    Per AC: must raise ValueError or return a rejection when given invalid
    input; does not return (True, '') for garbage input.
    """
    with pytest.raises(ValueError):
        demote_shell_script_ac("not-an-ac-at-all", tmp_path)

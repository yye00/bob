"""Tests for behavior-AC quoted-substring MUST-mention + MUST-NOT-use handler.

F-R7-591 hot-fix: when a behavior AC uses the form
  "behavior: ... MUST mention 'X' and MUST NOT use 'Y'"
the verifier does a workspace-wide substring grep rather than failing because
there is no function identifier in the criterion.

Acceptance criteria covered:
- test_must_mention_present_passes: MUST mention X, X in src/ → True + WARNING
- test_must_not_use_present_fails: MUST NOT use Y, Y in src/ → do NOT demote
- test_compound_pass_when_must_present_forbid_absent: both conditions hold → PASS
"""
from __future__ import annotations

import logging
import pathlib
import re

import pytest

from bob.enhanced_verification import _check_criterion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workspace(
    tmp_path: pathlib.Path,
    *,
    src_files: dict[str, str] | None = None,
) -> pathlib.Path:
    """Create a minimal workspace with src/ layout and reviews/findings.yaml."""
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (tmp_path / "pyproject.toml").write_text("[build-system]\n")
    reviews = tmp_path / "reviews"
    reviews.mkdir(exist_ok=True)
    (reviews / "findings.yaml").write_text("schema_version: 1\nfindings: []\n")

    if src_files:
        for rel_path, content in src_files.items():
            full = tmp_path / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)

    return tmp_path


def _run(workspace: pathlib.Path, criterion: str) -> bool:
    return _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


# ---------------------------------------------------------------------------
# AC: test_must_mention_present_passes
# ---------------------------------------------------------------------------


def test_must_mention_present_passes(tmp_path: pathlib.Path, caplog) -> None:
    """MUST mention X with X present in src/ → verifier returns True + WARNING.

    Corresponds to behavior AC:
      "when criterion text contains 'MUST mention X' with X a quoted literal,
       and at least one .py under src/ contains the literal X, the verifier
       MUST return True (demote with WARNING)"
    """
    workspace = _make_workspace(
        tmp_path,
        src_files={
            "src/bob/cli/__init__.py": (
                "# CLI module\nMESSAGE = 'Queue drained'\n"
            ),
        },
    )
    criterion = (
        "behavior: the CLI termination message for ALL_BLOCKED MUST mention "
        "'Queue drained' and MUST NOT use the phrase 'All remaining features are blocked'"
    )

    with caplog.at_level(logging.WARNING, logger="bob.enhanced_verification"):
        result = _run(workspace, criterion)

    assert result is True, (
        "Expected PASS (True) when MUST-mention literal is present in src/"
    )
    assert any(
        "F-R7-591 hot-fix" in record.message
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ), "Expected WARNING log tagged 'F-R7-591 hot-fix' but none found"


# ---------------------------------------------------------------------------
# AC: test_must_not_use_present_fails
# ---------------------------------------------------------------------------


def test_must_not_use_present_fails(tmp_path: pathlib.Path) -> None:
    """MUST NOT use Y with Y present in src/ → verifier must NOT demote (returns False).

    Corresponds to behavior AC:
      "when criterion text contains 'MUST NOT use Y' with Y a quoted literal,
       and at least one .py under src/ contains Y, the verifier MUST NOT demote
       (regression guard against silent over-demotion)"
    """
    workspace = _make_workspace(
        tmp_path,
        src_files={
            "src/bob/cli/__init__.py": (
                "# BAD: still uses forbidden phrase\n"
                "MESSAGE = 'All remaining features are blocked'\n"
            ),
        },
    )
    # Only a MUST NOT use constraint — the forbidden string IS present in src/
    criterion = (
        "behavior: the CLI MUST NOT use the phrase 'All remaining features are blocked'"
    )

    result = _run(workspace, criterion)

    assert result is False, (
        "Expected FAIL (False) when MUST-NOT-use literal IS present in src/ "
        "(regression guard: no silent over-demotion)"
    )


# ---------------------------------------------------------------------------
# AC: test_compound_pass_when_must_present_forbid_absent
# ---------------------------------------------------------------------------


def test_compound_pass_when_must_present_forbid_absent(
    tmp_path: pathlib.Path, caplog
) -> None:
    """Both MUST-mention and MUST-NOT-use: PASS only when both conditions hold.

    Corresponds to behavior AC:
      "when both MUST-mention and MUST-NOT-use are present, BOTH conditions
       must hold for demote-to-PASS"
    - MUST-mention literal present in src/  → mention_ok = True
    - MUST-NOT-use literal absent in src/   → forbid_ok  = True
    → returns True
    """
    workspace = _make_workspace(
        tmp_path,
        src_files={
            "src/bob/cli/__init__.py": (
                "# Correct implementation\n"
                "MESSAGE = 'Queue drained'\n"
                # NOTE: the forbidden phrase is intentionally absent
            ),
        },
    )
    criterion = (
        "behavior: the CLI termination message MUST mention 'Queue drained' "
        "and MUST NOT use the phrase 'All remaining features are blocked'"
    )

    with caplog.at_level(logging.WARNING, logger="bob.enhanced_verification"):
        result = _run(workspace, criterion)

    assert result is True, (
        "Expected PASS (True) when MUST-mention literal is present AND "
        "MUST-NOT-use literal is absent from src/"
    )

    warning_msgs = [
        r.message
        for r in caplog.records
        if r.levelno >= logging.WARNING and "F-R7-591 hot-fix" in r.message
    ]
    assert warning_msgs, "Expected at least one WARNING tagged 'F-R7-591 hot-fix'"

    # Both the must and forbid literals must appear in the warning message
    warning_text = warning_msgs[0]
    assert "Queue drained" in warning_text, (
        "WARNING must contain the must-mention literal 'Queue drained'"
    )
    assert "All remaining features are blocked" in warning_text, (
        "WARNING must contain the forbid literal 'All remaining features are blocked'"
    )

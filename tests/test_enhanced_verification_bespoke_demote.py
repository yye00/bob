"""Tests for F-R7-584: bespoke AC handlers demote-on-failure (return True) when
the target workspace module file exists, even if the strict bespoke check fails.

This prevents the bespoke verifier from causing NH loops when the spec asks a
module to implement behavior it hasn't gained yet — the module exists, so a
strict-check failure is an impl gap, not a missing-function condition.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from bob.enhanced_verification import _check_criterion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workspace_with_bap(
    tmp_path: pathlib.Path,
    bap_content: str,
) -> pathlib.Path:
    """Create a minimal workspace with a behavior_ac_parser.py stub."""
    bap_dir = tmp_path / "src" / "bob" / "spec_quality"
    bap_dir.mkdir(parents=True, exist_ok=True)
    (bap_dir / "behavior_ac_parser.py").write_text(bap_content)
    return tmp_path


def _make_workspace_without_bap(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a workspace where behavior_ac_parser.py is absent."""
    src_dir = tmp_path / "src" / "bob"
    src_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def _check(criterion: str, workspace: pathlib.Path) -> bool:
    return _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parse_behavior_ac_on_synonym_demotes(tmp_path, caplog):
    """When parse_behavior_ac exists but does not handle 'on synonym' yet,
    the bespoke handler must return True (demote) and emit an F-R7-584 warning.
    """
    # A stub parse_behavior_ac that returns an object missing conditional_keyword
    # == "on", so _ok is False — triggering the demotion path.
    bap_content = """
class _ParsedAC:
    def __init__(self, subject, condition, conditional_keyword="when"):
        self.subject = subject
        self.condition = condition
        self.conditional_keyword = conditional_keyword

def parse_behavior_ac(ac_text):
    # Stub: always returns "when" keyword (does not yet support "on")
    return _ParsedAC(subject="something", condition="condition", conditional_keyword="when")
"""
    workspace = _make_workspace_with_bap(tmp_path, bap_content)

    criterion = (
        "behavior: parse_behavior_ac returns a parsed tuple when the AC uses"
        " 'on <event>' as a synonym for 'when <condition>'"
    )

    with caplog.at_level(logging.WARNING, logger="bob.enhanced_verification"):
        result = _check(criterion, workspace)

    assert result is True, (
        "_check_criterion must return True (demote) when bespoke probe fails "
        "but module file exists"
    )
    assert any("F-R7-584" in record.message for record in caplog.records), (
        "Expected an F-R7-584 warning to be emitted when bespoke check fails "
        "but module exists"
    )


def test_parse_behavior_ac_compound_demotes(tmp_path, caplog):
    """When parse_behavior_ac exists but does not handle compound predicates yet,
    the bespoke handler must return True (demote) and emit an F-R7-584 warning.
    """
    # A stub parse_behavior_ac that raises to simulate compound-predicate path
    # not yet implemented — triggering the except branch demote path.
    bap_content = """
def parse_behavior_ac(ac_text):
    raise NotImplementedError("compound predicates not yet supported")
"""
    workspace = _make_workspace_with_bap(tmp_path, bap_content)

    criterion = (
        "behavior: parse_behavior_ac accepts compound predicates joined by 'and'"
        " as a single verifiable clause"
    )

    with caplog.at_level(logging.WARNING, logger="bob.enhanced_verification"):
        result = _check(criterion, workspace)

    assert result is True, (
        "_check_criterion must return True (demote) when bespoke probe raises "
        "but module file exists"
    )
    assert any("F-R7-584" in record.message for record in caplog.records), (
        "Expected an F-R7-584 warning to be emitted when bespoke probe raises "
        "but module exists"
    )


def test_missing_module_still_falls_through(tmp_path):
    """When behavior_ac_parser.py does NOT exist in the workspace, the bespoke
    branch must not trigger. The request falls through to F-R7-582 (or hard-fail
    if F-R7-582 also finds nothing). This guards against trivially returning True
    on missing modules.
    """
    # No behavior_ac_parser.py — workspace is empty of that file
    workspace = _make_workspace_without_bap(tmp_path)

    # Criterion that would normally trigger the 'on synonym' bespoke branch
    criterion = (
        "behavior: parse_behavior_ac returns a parsed tuple when the AC uses"
        " 'on <event>' as a synonym for 'when <condition>'"
    )

    result = _check(criterion, workspace)

    # Without the module, the bespoke branch is skipped. F-R7-582 may or may
    # not demote based on function names in the workspace. The critical
    # invariant is that we are NOT returning True because of the bespoke branch
    # (which would be a false positive on a missing module). Since this empty
    # workspace has no parse_behavior_ac definition anywhere, F-R7-582 will
    # also not find a match, so the result should be False.
    assert result is False, (
        "_check_criterion must NOT return True via the bespoke branch when the "
        "module file is absent — must fall through to F-R7-582 / hard-fail"
    )

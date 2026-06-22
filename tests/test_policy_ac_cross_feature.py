"""Tests for policy-AC demotion when criterion body contains F-RX-YYY reference.

F-R7-589 hot-fix: when an AC criterion text contains a cross-feature reference
token matching \\bF-R\\d+-\\d{3}\\b, the verifier demotes it to PASS with a
WARNING log line and emits a finding to reviews/findings.yaml tagged with
pattern 'policy-ac-cross-feature-reference'.
"""
from __future__ import annotations

import logging
import pathlib
import re
import tempfile

import pytest

from bob3.enhanced_verification import (
    _check_criterion,
    _emit_policy_ac_cross_feature_warning,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path):
    """Minimal workspace: pyproject.toml + src/bob3 + reviews/."""
    (tmp_path / "src" / "bob3").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[build-system]\n")
    (tmp_path / "reviews").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def findings_yaml(workspace):
    """Empty findings.yaml in the workspace/reviews/ directory."""
    p = workspace / "reviews" / "findings.yaml"
    p.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Required AC tests (must be module-level, named exactly as in the ACs)
# ---------------------------------------------------------------------------


def test_pass_when_f_r_ref_present(workspace):
    """Criterion containing F-RX-YYY token must be demoted to PASS (returns True)."""
    criterion = (
        "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    )
    result = _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert result is True, (
        "Expected PASS demotion for criterion containing F-R7-478 cross-feature ref"
    )


def test_fail_when_no_f_r_ref(workspace):
    """Criterion without F-RX-YYY token must NOT be silently demoted — hard-fail path."""
    # A behavior: criterion that mentions a completely unknown function with no
    # F-RX-YYY reference. The workspace src is empty so symbol-grep cannot
    # find it either.  Expect False (hard-fail), verifying no over-demotion.
    criterion = (
        "behavior: some_nonexistent_xyz_abc_func_qwerty returns a value"
    )
    result = _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert result is False, (
        "Expected hard-fail for behavior criterion with no F-RX-YYY token and no resolvable symbol"
    )


def test_warning_emitted_on_demotion(workspace, findings_yaml):
    """Demotion must write a finding to reviews/findings.yaml tagged policy-ac-cross-feature-reference."""
    criterion = "integration: regression-sweep / F-R7-532 invariant pass continues to run"
    _emit_policy_ac_cross_feature_warning(
        workspace=workspace,
        criterion=criterion,
        matched_token="F-R7-532",
    )

    content = findings_yaml.read_text(encoding="utf-8")
    assert "policy-ac-cross-feature-reference" in content, (
        "findings.yaml must be tagged with 'policy-ac-cross-feature-reference'"
    )
    assert "F-R7-532" in content, (
        "findings.yaml must include the matched F-RX-YYY token F-R7-532"
    )


# ---------------------------------------------------------------------------
# Additional regression / coverage tests
# ---------------------------------------------------------------------------


def test_warning_log_emitted_by_check_criterion(workspace, caplog):
    """_check_criterion logs a WARNING containing 'cross-feature' when demoting."""
    criterion = "integration: F-R7-478 path remains unaffected after change"
    with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
        result = _check_criterion(
            criterion=criterion,
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
    assert result is True
    assert any(
        "cross-feature" in rec.message.lower() or "policy-ac demoted" in rec.message.lower()
        for rec in caplog.records
    ), f"Expected cross-feature/policy-AC demoted WARNING; got: {[r.message for r in caplog.records]}"


def test_multiple_f_r_refs_demoted(workspace):
    """Criterion with multiple F-RX-YYY tokens is demoted on the first match."""
    criterion = (
        "integration: F-R7-478 and F-R7-479 feature definitions in the merged spec"
    )
    result = _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert result is True, "Expected PASS demotion for criterion with multiple F-RX-YYY refs"


def test_behavior_criterion_no_fr_ref_hard_fails(workspace):
    """behavior: criterion without F-RX-YYY and no resolvable symbol -> False (no over-demotion)."""
    criterion = "behavior: when_the_module encounters an error it logs a specific_line_here"
    result = _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    # The workspace src is empty; symbol-grep can't resolve it either.
    # Must NOT silently PASS — over-demotion guard.
    assert result is False, (
        "behavior criterion with no F-RX-YYY token and no resolving symbol must not silently PASS"
    )


def test_emit_warning_creates_findings_yaml_if_missing(workspace):
    """_emit_policy_ac_cross_feature_warning creates findings.yaml when it does not exist."""
    findings_path = workspace / "reviews" / "findings.yaml"
    assert not findings_path.exists()

    _emit_policy_ac_cross_feature_warning(
        workspace=workspace,
        criterion="integration: F-R7-999 some claim",
        matched_token="F-R7-999",
    )

    assert findings_path.exists(), "findings.yaml should be created by the warning emitter"
    content = findings_path.read_text(encoding="utf-8")
    assert "policy-ac-cross-feature-reference" in content
    assert "F-R7-999" in content

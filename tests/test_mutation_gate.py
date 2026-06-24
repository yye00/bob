"""Tests for bob73.mutation_gate (AC: pytest: tests/test_mutation_gate.py).

Verifies that bob73.mutation_gate re-exports the full mutation gate API from
bob.verification.mutation_gate and that run_mutation_test is callable.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import bob73.mutation_gate as mg
from bob73.mutation_gate import (
    MutationReport,
    MutmutMissingError,
    default_threshold,
    mutation_operators,
    never_mutates_failing_impl,
    passes_gate,
    persist_surviving_mutants,
    run_mutation_test,
    runs_only_after_pytest_pass,
)


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def test_run_mutation_test_is_callable():
    """AC: Function defined: bob73.mutation_gate.run_mutation_test."""
    assert callable(run_mutation_test)


def test_module_exports_all_public_symbols():
    """All expected public names are present in bob73.mutation_gate."""
    expected = [
        "run_mutation_test",
        "MutationReport",
        "MutmutMissingError",
        "passes_gate",
        "persist_surviving_mutants",
        "default_threshold",
        "mutation_operators",
        "runs_only_after_pytest_pass",
        "never_mutates_failing_impl",
    ]
    for name in expected:
        assert hasattr(mg, name), f"bob73.mutation_gate is missing {name!r}"


# ---------------------------------------------------------------------------
# Behavioural delegation — gate logic
# ---------------------------------------------------------------------------


def test_passes_gate_above_threshold():
    assert passes_gate(0.80) is True


def test_passes_gate_at_threshold():
    assert passes_gate(0.75) is True


def test_passes_gate_below_threshold():
    assert passes_gate(0.74) is False


def test_default_threshold_is_0_75():
    assert default_threshold() == 0.75


def test_mutation_operators_returns_list():
    ops = mutation_operators()
    assert isinstance(ops, list)
    assert len(ops) > 0


def test_runs_only_after_pytest_pass_false():
    assert runs_only_after_pytest_pass(False) is False


def test_runs_only_after_pytest_pass_true():
    assert runs_only_after_pytest_pass(True) is True


def test_never_mutates_failing_impl():
    assert never_mutates_failing_impl() is True


# ---------------------------------------------------------------------------
# persist_surviving_mutants writes correct JSON
# ---------------------------------------------------------------------------


def test_persist_surviving_mutants_creates_report(tmp_path):
    report = MutationReport(
        feature_id="feat-test",
        total_mutants=10,
        killed=7,
        survived=3,
        timed_out=0,
        mutation_score=0.70,
        surviving_mutant_diffs=[{"mutant_id": "m1", "diff": "--- a\n+++ b\n"}],
    )
    out_path = persist_surviving_mutants(report, tmp_path)

    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data["feature_id"] == "feat-test"
    assert data["mutation_score"] == 0.70
    assert "surviving_mutant_diffs" in data
    assert "strengthen assertions" in data.get("message", "")


# ---------------------------------------------------------------------------
# run_mutation_test raises MutmutMissingError when mutmut absent
# ---------------------------------------------------------------------------


def test_run_mutation_test_raises_when_mutmut_missing(tmp_path):
    src_file = tmp_path / "dummy.py"
    src_file.write_text("x = 1\n")

    with patch("bob.verification.mutation_gate.shutil.which", return_value=None):
        with pytest.raises(MutmutMissingError):
            run_mutation_test(
                feature_id="feat-x",
                src_files=[src_file],
                test_dir=str(tmp_path),
                workspace=str(tmp_path),
            )


# ---------------------------------------------------------------------------
# MutationReport dataclass
# ---------------------------------------------------------------------------


def test_mutation_report_fields():
    r = MutationReport(
        feature_id="f1",
        total_mutants=5,
        killed=4,
        survived=1,
        timed_out=0,
        mutation_score=0.80,
    )
    assert r.feature_id == "f1"
    assert r.total_mutants == 5
    assert r.mutation_score == 0.80
    assert r.timed_out_early is False
    assert r.partial is False
    assert r.surviving_mutant_diffs == []

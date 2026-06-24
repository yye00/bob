"""Golden corpus tests for spec_quality_score.compute().

5 frozen golden specs (3 good, 2 bad) with frozen expected composite scores.
These anchor the scorer in CI so the rubric itself can regress-test.

Good specs have composite >= 0.80.
Bad specs have composite < 0.65.

Expected scores are frozen at implementation time. If the algorithm changes
and scores shift, these tests will catch it.
"""

from __future__ import annotations

import pytest
import sys
import os

# tools/ is not a package — add it to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from spec_quality_score import compute, GATE_BLOCK, GATE_WARN


# ---------------------------------------------------------------------------
# Golden corpus: 3 good specs
# ---------------------------------------------------------------------------

_GOOD_1_NAME = "Composite spec_quality_score"
_GOOD_1_DESC = """
Replaces the F-R7-413 placeholder with a concrete weighted geometric mean of
8 sub-metrics: smell_density (0.20), predicate_coverage (0.20),
contract_completeness (0.15), boundary_coverage (0.10), error_path_coverage (0.10),
traceability (0.10), spec_executability (0.10), ac_atomicity (0.05).
Function compute returns CompositeScore with all sub-metrics.
File tools/spec_quality_score.py exists.
"""
_GOOD_1_ACS = [
    "File exists: tools/spec_quality_score.py",
    "Function defined: spec_quality_score.compute",
    "pytest: tests/test_spec_quality_score_golden_corpus.py",
    "pytest: tests/test_spec_quality_score_gates_plan_create.py",
    "pytest: tests/test_spec_quality_score_one_zero_dominates.py",
    "Score < 0.65 makes `bob plan --create` exit non-zero with rationale",
    "integration: bob.cli.plan",
]

_GOOD_2_NAME = "Disk-state reconciler"
_GOOD_2_DESC = """
Add reconcile_from_disk(project_id). For each feature in status='pending'
or status='ready', check whether all File exists: and pytest: ACs already
pass on disk. If all pass, promote to status='completed'.
Raises ValueError on invalid project_id.
"""
_GOOD_2_ACS = [
    "File exists: src/bob/disk_reconciler.py",
    "Function defined: bob.disk_reconciler.reconcile_from_disk",
    "pytest: tests/test_disk_reconciler.py",
    "Score < 0.65 makes plan exit non-zero",
    "integration: bob.cli.run",
]

_GOOD_3_NAME = "Convergence detector"
_GOOD_3_DESC = """
The current check_convergence compares feature sets by UUID.
Feature IDs are minted as fresh UUIDs in every bob init.
Add a stable spec_slot column to the features table.
Raises ValueError when spec_slot is empty.
"""
_GOOD_3_ACS = [
    "File exists: src/bob/migrations/add_spec_slot.py",
    "Function defined: bob.migrations.add_spec_slot.upgrade",
    "Field exists on Feature model: spec_slot",
    "pytest: tests/test_spec_slot_migration.py",
    "pytest: tests/test_convergence_by_spec_slot.py",
    "integration: tools/weekend_watchdog.sh:check_convergence",
    "Score raises ValueError when spec_slot is empty or null",
]


# ---------------------------------------------------------------------------
# Golden corpus: 2 bad specs
# ---------------------------------------------------------------------------

_BAD_1_NAME = "Fast and reliable auth"
_BAD_1_DESC = "Build a fast, simple, and reliable authentication system."
_BAD_1_ACS = [
    "The system should work correctly",
    "Users should be able to authenticate easily",
    "The auth should be fast and reliable",
    "Handles all edge cases properly",
    "Supports various authentication methods",
]

_BAD_2_NAME = "Beautiful dashboard"
_BAD_2_DESC = "Create a beautiful, intuitive dashboard with smooth transitions."
_BAD_2_ACS = [
    "Dashboard is clean and modern",
    "UI is elegant and seamless",
    "Everything works nicely together",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGoodSpec1:
    def test_composite_is_green(self):
        result = compute(_GOOD_1_NAME, _GOOD_1_DESC, _GOOD_1_ACS)
        assert result.composite >= GATE_WARN, (
            f"Good spec 1 expected >= {GATE_WARN}, got {result.composite:.4f}\n"
            f"Rationale: {result.rationale}"
        )

    def test_returns_all_sub_metrics(self):
        result = compute(_GOOD_1_NAME, _GOOD_1_DESC, _GOOD_1_ACS)
        assert 0.0 <= result.smell_density <= 1.0
        assert 0.0 <= result.predicate_coverage <= 1.0
        assert 0.0 <= result.contract_completeness <= 1.0
        assert 0.0 <= result.boundary_coverage <= 1.0
        assert 0.0 <= result.error_path_coverage <= 1.0
        assert 0.0 <= result.traceability <= 1.0
        assert 0.0 <= result.spec_executability <= 1.0
        assert 0.0 <= result.ac_atomicity <= 1.0


class TestGoodSpec2:
    def test_composite_is_green(self):
        result = compute(_GOOD_2_NAME, _GOOD_2_DESC, _GOOD_2_ACS)
        assert result.composite >= GATE_WARN, (
            f"Good spec 2 expected >= {GATE_WARN}, got {result.composite:.4f}\n"
            f"Rationale: {result.rationale}"
        )


class TestGoodSpec3:
    def test_composite_is_green(self):
        result = compute(_GOOD_3_NAME, _GOOD_3_DESC, _GOOD_3_ACS)
        assert result.composite >= GATE_WARN, (
            f"Good spec 3 expected >= {GATE_WARN}, got {result.composite:.4f}\n"
            f"Rationale: {result.rationale}"
        )


_DEFAULT_GATE_BLOCK = 0.65  # canonical default — env may lower it for operator unstick


class TestBadSpec1:
    def test_composite_is_blocked(self):
        result = compute(_BAD_1_NAME, _BAD_1_DESC, _BAD_1_ACS)
        assert result.composite < _DEFAULT_GATE_BLOCK, (
            f"Bad spec 1 expected < {_DEFAULT_GATE_BLOCK}, got {result.composite:.4f}"
        )

    def test_smell_density_is_low(self):
        result = compute(_BAD_1_NAME, _BAD_1_DESC, _BAD_1_ACS)
        # Bad spec has many E-smells, composite driven to 0 by zero predicate_coverage
        # At least some ACs must have smells detected
        assert result.smell_density < 1.0, (
            f"Expected smell_density < 1.0 for bad spec 1, got {result.smell_density:.4f}"
        )
        # Composite must be blocked (below default 0.65 threshold, regardless of env override)
        assert result.composite < _DEFAULT_GATE_BLOCK


class TestBadSpec2:
    def test_composite_is_blocked(self):
        result = compute(_BAD_2_NAME, _BAD_2_DESC, _BAD_2_ACS)
        assert result.composite < _DEFAULT_GATE_BLOCK, (
            f"Bad spec 2 expected < {_DEFAULT_GATE_BLOCK}, got {result.composite:.4f}"
        )

    def test_smell_density_is_zero(self):
        result = compute(_BAD_2_NAME, _BAD_2_DESC, _BAD_2_ACS)
        # Every AC in bad spec 2 has E-smells
        assert result.smell_density < 0.5, (
            f"Expected smell_density < 0.5 for bad spec 2, got {result.smell_density:.4f}"
        )


class TestAsDict:
    def test_as_dict_structure(self):
        result = compute(_GOOD_1_NAME, _GOOD_1_DESC, _GOOD_1_ACS)
        d = result.as_dict()
        assert "composite" in d
        assert "sub_metrics" in d
        assert "weights" in d
        assert set(d["sub_metrics"].keys()) == {
            "smell_density", "predicate_coverage", "contract_completeness",
            "boundary_coverage", "error_path_coverage", "traceability",
            "spec_executability", "ac_atomicity",
        }
        assert abs(sum(d["weights"].values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Frozen score regression tests (anchored at implementation time)
# These verify the scorer does not silently drift.
# ---------------------------------------------------------------------------

_TOLERANCE = 1e-4  # allow rounding differences across Python versions


class TestFrozenScores:
    """Frozen composite scores for all 5 golden corpus specs.

    If the algorithm changes and scores shift, these tests will catch it.
    Tolerance: ±0.0001 to allow minor floating-point differences.
    """

    def test_good1_frozen_composite(self):
        result = compute(_GOOD_1_NAME, _GOOD_1_DESC, _GOOD_1_ACS)
        assert abs(result.composite - 0.906536) < _TOLERANCE, (
            f"Good spec 1 frozen composite changed: expected ~0.906536, got {result.composite:.6f}"
        )

    def test_good2_frozen_composite(self):
        result = compute(_GOOD_2_NAME, _GOOD_2_DESC, _GOOD_2_ACS)
        assert abs(result.composite - 0.956352) < _TOLERANCE, (
            f"Good spec 2 frozen composite changed: expected ~0.956352, got {result.composite:.6f}"
        )

    def test_good3_frozen_composite(self):
        result = compute(_GOOD_3_NAME, _GOOD_3_DESC, _GOOD_3_ACS)
        assert abs(result.composite - 0.879014) < _TOLERANCE, (
            f"Good spec 3 frozen composite changed: expected ~0.879014, got {result.composite:.6f}"
        )

    def test_bad1_frozen_composite(self):
        result = compute(_BAD_1_NAME, _BAD_1_DESC, _BAD_1_ACS)
        assert result.composite == 0.0, (
            f"Bad spec 1 frozen composite changed: expected 0.0, got {result.composite:.6f}"
        )

    def test_bad2_frozen_composite(self):
        result = compute(_BAD_2_NAME, _BAD_2_DESC, _BAD_2_ACS)
        assert result.composite == 0.0, (
            f"Bad spec 2 frozen composite changed: expected 0.0, got {result.composite:.6f}"
        )

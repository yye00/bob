"""Tests for bidirectional_requirements_traceability_matrix_rtm_artifact module."""

from __future__ import annotations

import json
import pathlib

import pytest


def test_bidirectional_requirements_traceability_matrix_rtm_artifact():
    """Smoke test: the main function is importable and callable, returning an RTM dict."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    result = bidirectional_requirements_traceability_matrix_rtm_artifact(
        workspace=".",
        feature_id="test-feature-001",
        acs=[{"id": "AC-01", "text": "Function exists and is callable"}],
        test_contents={"tests/test_example.py": "AC-01 is tested here"},
        src_functions=[],
    )

    assert isinstance(result, dict)
    assert "spec_coverage_pct" in result
    assert "acs" in result
    assert "untraced_implementations" in result
    assert "feature_id" in result
    assert result["feature_id"] == "test-feature-001"


def test_forward_traceability_covered_ac():
    """AC covered by a test file should not be flagged as orphan."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    result = bidirectional_requirements_traceability_matrix_rtm_artifact(
        workspace=".",
        feature_id="feat-forward",
        acs=[{"id": "AC-01", "text": "build_rtm function is callable"}],
        test_contents={"tests/test_foo.py": "AC-01 build_rtm is called in this test"},
        src_functions=[],
    )

    ac_record = result["acs"].get("AC-01") or next(iter(result["acs"].values()))
    assert ac_record["orphan"] is False
    assert result["spec_coverage_pct"] == 1.0


def test_forward_traceability_orphaned_ac():
    """AC with no matching test should be flagged as orphan."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    result = bidirectional_requirements_traceability_matrix_rtm_artifact(
        workspace=".",
        feature_id="feat-orphan",
        acs=[{"id": "AC-99", "text": "completely unrelated requirement xyz"}],
        test_contents={"tests/test_other.py": "nothing relevant here at all"},
        src_functions=[],
    )

    ac_record = result["acs"].get("AC-99") or next(iter(result["acs"].values()))
    assert ac_record["orphan"] is True
    assert result["spec_coverage_pct"] == 0.0


def test_halt_gate_passes_above_threshold():
    """check_halt_gate returns True when spec_coverage_pct >= 0.80."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        check_halt_gate,
    )

    passed, reason = check_halt_gate({"spec_coverage_pct": 0.90})
    assert passed is True
    assert reason == ""


def test_halt_gate_fails_below_threshold():
    """check_halt_gate returns False when spec_coverage_pct < 0.80."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        check_halt_gate,
    )

    passed, reason = check_halt_gate({"spec_coverage_pct": 0.70})
    assert passed is False
    assert "0.80" in reason or "halt" in reason.lower() or "threshold" in reason.lower()


def test_halt_gate_exactly_at_threshold():
    """check_halt_gate passes at exactly 0.80."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        check_halt_gate,
    )

    passed, _ = check_halt_gate({"spec_coverage_pct": 0.80})
    assert passed is True


def test_backward_traceability_flags_untraced_function():
    """Function in src without AC link should appear in untraced_implementations."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    result = bidirectional_requirements_traceability_matrix_rtm_artifact(
        workspace=".",
        feature_id="feat-backward",
        acs=[{"id": "AC-01", "text": "some requirement about other stuff"}],
        test_contents={"tests/test_basic.py": "AC-01 tested here"},
        src_functions=[
            {"function": "completely_unrelated_mystery_func", "file": "src/bob3/something.py"}
        ],
    )

    untraced_names = [fn["function"] for fn in result["untraced_implementations"]]
    assert "completely_unrelated_mystery_func" in untraced_names


def test_backward_traceability_linked_function_not_flagged():
    """Function referenced in an AC should NOT appear in untraced_implementations."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    result = bidirectional_requirements_traceability_matrix_rtm_artifact(
        workspace=".",
        feature_id="feat-linked",
        acs=[{"id": "AC-01", "text": "Function: my_linked_function is defined"}],
        test_contents={"tests/test_linked.py": "AC-01 my_linked_function tested"},
        src_functions=[
            {"function": "my_linked_function", "file": "src/bob3/something.py"}
        ],
    )

    untraced_names = [fn["function"] for fn in result["untraced_implementations"]]
    assert "my_linked_function" not in untraced_names


def test_zero_acs_returns_zero_coverage():
    """Zero ACs should yield spec_coverage_pct=0.0 without division errors."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    result = bidirectional_requirements_traceability_matrix_rtm_artifact(
        workspace=".",
        feature_id="feat-empty",
        acs=[],
        test_contents={},
        src_functions=[],
    )

    assert result["spec_coverage_pct"] == 0.0
    assert result["acs"] == {}
    assert result["untraced_implementations"] == []


def test_multiple_acs_partial_coverage():
    """Two ACs, one covered and one orphaned → spec_coverage_pct=0.5."""
    from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    result = bidirectional_requirements_traceability_matrix_rtm_artifact(
        workspace=".",
        feature_id="feat-partial",
        acs=[
            {"id": "AC-01", "text": "covered requirement"},
            {"id": "AC-02", "text": "orphaned requirement xyz_unique_99"},
        ],
        test_contents={"tests/test_partial.py": "AC-01 covered requirement tested"},
        src_functions=[],
    )

    assert result["spec_coverage_pct"] == pytest.approx(0.5)

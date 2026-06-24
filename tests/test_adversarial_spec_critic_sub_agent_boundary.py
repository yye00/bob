"""Boundary tests for spec_critic.run_critic.

AC: empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_critic import run_critic


_CONSTITUTION_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "bob3" / "spec_quality" / "spec_constitution.md"
)


# ---------------------------------------------------------------------------
# Boundary: empty acceptance criteria list
# ---------------------------------------------------------------------------

class TestEmptyAcceptanceCriteria:
    def test_empty_ac_list_returns_dict(self, tmp_path):
        result = run_critic(
            feature_id="boundary-empty-ac",
            name="Empty ACs",
            description="Feature with no ACs.",
            acceptance_criteria=[],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert isinstance(result, dict)

    def test_empty_ac_list_has_required_keys(self, tmp_path):
        result = run_critic(
            feature_id="boundary-empty-ac-2",
            name="Empty ACs 2",
            description="desc",
            acceptance_criteria=[],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert "gate_passed" in result
        assert "defects" in result
        assert "spec_hash" in result

    def test_empty_ac_list_does_not_raise(self, tmp_path):
        # Empty list is a valid input — should produce a result, not an exception
        try:
            run_critic(
                feature_id="boundary-no-raise",
                name="No raise",
                description="desc",
                acceptance_criteria=[],
                constitution_path=_CONSTITUTION_PATH,
                findings_path=tmp_path / "sf.yaml",
            )
        except Exception as exc:
            pytest.fail(f"run_critic raised unexpectedly on empty AC list: {exc}")

    def test_empty_ac_list_gate_passed_is_bool(self, tmp_path):
        result = run_critic(
            feature_id="boundary-bool",
            name="Bool check",
            description="desc",
            acceptance_criteria=[],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert isinstance(result["gate_passed"], bool)

    def test_empty_ac_list_defects_is_list(self, tmp_path):
        result = run_critic(
            feature_id="boundary-defects-list",
            name="Defects list",
            description="desc",
            acceptance_criteria=[],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert isinstance(result["defects"], list)


# ---------------------------------------------------------------------------
# Boundary: minimum valid input (single AC)
# ---------------------------------------------------------------------------

class TestMinimumValidInput:
    def test_single_ac_returns_result(self, tmp_path):
        result = run_critic(
            feature_id="boundary-min",
            name="Minimum",
            description="d",
            acceptance_criteria=["pytest: tests/test_min_error.py"],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert isinstance(result, dict)
        assert "gate_passed" in result

    def test_single_structured_ac_no_crash(self, tmp_path):
        try:
            run_critic(
                feature_id="boundary-single-struct",
                name="Single struct",
                description="d",
                acceptance_criteria=["File exists: src/x.py"],
                constitution_path=_CONSTITUTION_PATH,
                findings_path=tmp_path / "sf.yaml",
            )
        except Exception as exc:
            pytest.fail(f"Unexpected exception on single AC: {exc}")

    def test_empty_name_does_not_raise(self, tmp_path):
        result = run_critic(
            feature_id="boundary-empty-name",
            name="",
            description="d",
            acceptance_criteria=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert isinstance(result, dict)

    def test_empty_description_does_not_raise(self, tmp_path):
        result = run_critic(
            feature_id="boundary-empty-desc",
            name="Name",
            description="",
            acceptance_criteria=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Boundary: spec_hash is always a non-empty string
# ---------------------------------------------------------------------------

class TestSpecHashBoundary:
    def test_spec_hash_nonempty_for_empty_acs(self, tmp_path):
        result = run_critic(
            feature_id="boundary-hash-empty",
            name="Hash empty ACs",
            description="d",
            acceptance_criteria=[],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert isinstance(result["spec_hash"], str)
        assert len(result["spec_hash"]) > 0

    def test_spec_hash_16_chars(self, tmp_path):
        result = run_critic(
            feature_id="boundary-hash-len",
            name="Hash len",
            description="d",
            acceptance_criteria=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "sf.yaml",
        )
        assert len(result["spec_hash"]) == 16

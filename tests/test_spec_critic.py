"""Tests for src/spec_critic.py — the top-level run_critic entry point.

Acceptance criteria:
  - File exists: src/spec_critic.py
  - Function defined: spec_critic.run_critic
  - File exists: reviews/spec_findings.yaml
  - integration: bob.spec_quality.spec_extractor
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_critic import run_critic, ConstitutionMissingError


_CONSTITUTION_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "bob" / "spec_quality" / "spec_constitution.md"
)

_REVIEWS_DIR = Path(__file__).resolve().parents[1] / "reviews"


# ---------------------------------------------------------------------------
# File and function existence
# ---------------------------------------------------------------------------

class TestFileAndFunctionExist:
    def test_spec_critic_module_importable(self):
        import spec_critic
        assert hasattr(spec_critic, "run_critic")

    def test_reviews_spec_findings_yaml_exists(self):
        assert (_REVIEWS_DIR / "spec_findings.yaml").exists(), (
            "reviews/spec_findings.yaml must exist"
        )

    def test_run_critic_callable(self):
        assert callable(run_critic)


# ---------------------------------------------------------------------------
# Integration: spec_extractor reachability
# ---------------------------------------------------------------------------

class TestSpecExtractorIntegration:
    def test_spec_extractor_importable(self):
        from bob.spec_quality.spec_extractor import extract_acs
        assert callable(extract_acs)

    def test_run_critic_after_extraction(self, tmp_path):
        result = run_critic(
            feature_id="integ-001",
            name="Integration test",
            description="Tests integration with spec_extractor.",
            acceptance_criteria=[
                "File exists: src/bob/spec_quality/spec_extractor.py",
                "pytest: tests/test_spec_extractor_error.py",
            ],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "spec_findings.yaml",
        )
        assert isinstance(result, dict)
        assert "gate_passed" in result


# ---------------------------------------------------------------------------
# run_critic — happy path (clean spec)
# ---------------------------------------------------------------------------

class TestRunCriticCleanSpec:
    def test_clean_spec_gate_passed(self, tmp_path):
        result = run_critic(
            feature_id="clean-001",
            name="Clean feature",
            description="Implements a structured logging pipeline.",
            acceptance_criteria=[
                "File exists: src/bob/logger.py",
                "Function defined: bob.logger.log_event",
                "pytest: tests/test_logger.py",
                "pytest: tests/test_logger_invalid_payload.py",
            ],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "spec_findings.yaml",
        )
        assert result["gate_passed"] is True
        assert result["defects"] == []
        assert isinstance(result["spec_hash"], str)
        assert len(result["spec_hash"]) == 16

    def test_result_has_required_keys(self, tmp_path):
        result = run_critic(
            feature_id="keys-001",
            name="Keys test",
            description="desc",
            acceptance_criteria=[
                "File exists: src/x.py",
                "pytest: tests/test_x_error.py",
            ],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "spec_findings.yaml",
        )
        assert set(result.keys()) >= {"gate_passed", "defects", "spec_hash"}


# ---------------------------------------------------------------------------
# run_critic — defects detected
# ---------------------------------------------------------------------------

class TestRunCriticDefectsDetected:
    def test_ambiguous_spec_gate_fails(self, tmp_path):
        result = run_critic(
            feature_id="bad-001",
            name="Ambiguous feature",
            description="Does something.",
            acceptance_criteria=[
                "The module works correctly",
            ],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "spec_findings.yaml",
        )
        assert result["gate_passed"] is False
        assert len(result["defects"]) > 0

    def test_defects_have_required_fields(self, tmp_path):
        result = run_critic(
            feature_id="fields-001",
            name="Fields test",
            description="desc",
            acceptance_criteria=[
                "The module works correctly",
            ],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "spec_findings.yaml",
        )
        for defect in result["defects"]:
            assert "feature_id" in defect
            assert "ac_index" in defect
            assert "defect_type" in defect
            assert "rationale" in defect
            assert "suggested_fix" in defect

    def test_missing_edge_case_detected(self, tmp_path):
        result = run_critic(
            feature_id="ec-001",
            name="Happy path only",
            description="desc",
            acceptance_criteria=[
                "File exists: src/foo.py",
                "Function defined: foo.bar",
                "pytest: tests/test_foo.py",
            ],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "spec_findings.yaml",
        )
        defect_types = {d["defect_type"] for d in result["defects"]}
        assert "missing_edge_case" in defect_types


# ---------------------------------------------------------------------------
# run_critic — persistence
# ---------------------------------------------------------------------------

class TestRunCriticPersistence:
    def test_persists_to_findings_path(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        run_critic(
            feature_id="persist-001",
            name="Persist test",
            description="desc",
            acceptance_criteria=[
                "File exists: src/persist.py",
                "pytest: tests/test_persist_error.py",
            ],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=findings_path,
        )
        assert findings_path.exists()

    def test_spec_hash_deterministic(self, tmp_path):
        kwargs = dict(
            feature_id="det-001",
            name="Deterministic",
            description="desc",
            acceptance_criteria=["File exists: src/det.py", "pytest: tests/test_det_error.py"],
            constitution_path=_CONSTITUTION_PATH,
            findings_path=tmp_path / "spec_findings.yaml",
        )
        r1 = run_critic(**kwargs)
        r2 = run_critic(**kwargs)
        assert r1["spec_hash"] == r2["spec_hash"]


# ---------------------------------------------------------------------------
# run_critic — missing constitution
# ---------------------------------------------------------------------------

class TestRunCriticMissingConstitution:
    def test_raises_constitution_missing_error(self, tmp_path):
        with pytest.raises(ConstitutionMissingError):
            run_critic(
                feature_id="miss-001",
                name="Missing constitution",
                description="desc",
                acceptance_criteria=["File exists: src/miss.py", "pytest: tests/test_miss_error.py"],
                constitution_path=tmp_path / "nonexistent_constitution.md",
                findings_path=tmp_path / "spec_findings.yaml",
            )

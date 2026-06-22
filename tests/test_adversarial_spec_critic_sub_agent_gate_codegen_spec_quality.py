"""Tests for adversarial_spec_critic_sub_agent_gate_codegen_spec_quality.

Acceptance criteria:
  - File exists: src/bob3/adversarial_spec_critic_sub_agent_gate_codegen_spec_quality.py
  - pytest: tests/test_adversarial_spec_critic_sub_agent_gate_codegen_spec_quality.py::test_adversarial_spec_critic_sub_agent_gate_codegen_spec_quality
  - Function defined: bob3.adversarial_spec_critic_sub_agent_gate_codegen_spec_quality.adversarial_spec_critic_sub_agent_gate_codegen_spec_quality
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------

from bob3.adversarial_spec_critic_sub_agent_gate_codegen_spec_quality import (
    adversarial_spec_critic_sub_agent_gate_codegen_spec_quality,
)


# ---------------------------------------------------------------------------
# Required by AC: single named test
# ---------------------------------------------------------------------------

def test_adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(tmp_path):
    """Primary acceptance-criteria test — covers all core behaviours."""
    constitution_path = (
        Path(__file__).resolve().parents[1]
        / "src" / "bob3" / "spec_quality" / "spec_constitution.md"
    )

    # --- 1. Clean spec returns gate_passed=True and no defects ---
    result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
        feature_id="clean-feat-001",
        name="Clean feature",
        description="Implements a structured logging pipeline.",
        acceptance_criteria=[
            "File exists: src/bob3/logger.py",
            "Function defined: bob3.logger.log_event",
            "pytest: tests/test_logger.py",
            "pytest: tests/test_logger_invalid_payload.py",
        ],
        findings_path=tmp_path / "spec_findings.yaml",
        constitution_path=constitution_path,
    )

    assert isinstance(result, dict), "result must be a dict"
    assert "gate_passed" in result, "result must have 'gate_passed'"
    assert "defects" in result, "result must have 'defects'"
    assert "spec_hash" in result, "result must have 'spec_hash'"
    assert result["gate_passed"] is True
    assert isinstance(result["defects"], list)
    assert result["defects"] == []
    assert isinstance(result["spec_hash"], str)
    assert len(result["spec_hash"]) > 0

    # --- 2. Ambiguous spec returns gate_passed=False with defects ---
    result_bad = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
        feature_id="bad-feat-001",
        name="Ambiguous feature",
        description="Does something.",
        acceptance_criteria=[
            "The module works correctly",
        ],
        findings_path=tmp_path / "spec_findings.yaml",
        constitution_path=constitution_path,
    )

    assert result_bad["gate_passed"] is False
    assert len(result_bad["defects"]) > 0
    defect_types = {d["defect_type"] for d in result_bad["defects"]}
    assert defect_types & {"ambiguity", "missing_edge_case"}, (
        f"expected ambiguity or missing_edge_case, got {defect_types}"
    )

    # --- 3. Findings persist to the spec_findings.yaml keyed by spec_hash ---
    findings_file = tmp_path / "spec_findings.yaml"
    assert findings_file.exists(), "findings must be persisted to spec_findings.yaml"

    import yaml
    data = yaml.safe_load(findings_file.read_text())
    spec_hash = result_bad["spec_hash"]
    assert spec_hash in data.get("findings_by_hash", {}), (
        f"spec_hash {spec_hash!r} not found in persisted findings"
    )

    # --- 4. Constitution path must exist or raise ConstitutionMissingError ---
    from bob3.spec_quality.spec_critic import ConstitutionMissingError
    with pytest.raises(ConstitutionMissingError):
        adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="x",
            name="x",
            description="x",
            acceptance_criteria=["pytest: tests/test_x_error.py"],
            findings_path=tmp_path / "sf2.yaml",
            constitution_path=tmp_path / "nonexistent_constitution.md",
        )

    # --- 5. Each defect has required fields ---
    for defect in result_bad["defects"]:
        assert "feature_id" in defect
        assert "ac_index" in defect
        assert "defect_type" in defect
        assert "rationale" in defect
        assert "suggested_fix" in defect

    # --- 6. spec_hash is deterministic for the same input ---
    result2 = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
        feature_id="bad-feat-001",
        name="Ambiguous feature",
        description="Does something.",
        acceptance_criteria=[
            "The module works correctly",
        ],
        findings_path=tmp_path / "sf3.yaml",
        constitution_path=constitution_path,
    )
    assert result2["spec_hash"] == result_bad["spec_hash"], (
        "spec_hash must be deterministic for identical inputs"
    )


# ---------------------------------------------------------------------------
# Additional unit tests
# ---------------------------------------------------------------------------

class TestAdversarialSpecCriticGateCodegen:
    """Unit tests for the adversarial gate function."""

    @pytest.fixture
    def constitution_path(self):
        return (
            Path(__file__).resolve().parents[1]
            / "src" / "bob3" / "spec_quality" / "spec_constitution.md"
        )

    def test_returns_dict(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="r-001",
            name="Returns dict",
            description="desc",
            acceptance_criteria=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        assert isinstance(result, dict)

    def test_gate_passed_for_clean_spec(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="g-001",
            name="Clean",
            description="desc",
            acceptance_criteria=[
                "File exists: src/clean.py",
                "pytest: tests/test_clean_error.py",
            ],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        assert result["gate_passed"] is True
        assert result["defects"] == []

    def test_gate_failed_for_vague_quantifier(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="vq-001",
            name="Perf feature",
            description="desc",
            acceptance_criteria=[
                "Responses are fast enough",
                "pytest: tests/test_perf_timeout.py",
            ],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        assert result["gate_passed"] is False
        defect_types = {d["defect_type"] for d in result["defects"]}
        assert "vague_quantifier" in defect_types

    def test_gate_failed_for_missing_edge_case(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="ec-001",
            name="Happy path only",
            description="desc",
            acceptance_criteria=[
                "File exists: src/feature.py",
                "Function defined: feature.run",
            ],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        assert result["gate_passed"] is False
        defect_types = {d["defect_type"] for d in result["defects"]}
        assert "missing_edge_case" in defect_types

    def test_spec_hash_in_result(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="h-001",
            name="Hash test",
            description="desc",
            acceptance_criteria=["File exists: src/h.py", "pytest: tests/test_h_error.py"],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        assert isinstance(result["spec_hash"], str)
        assert len(result["spec_hash"]) == 16  # truncated SHA-256

    def test_findings_persisted_to_yaml(self, tmp_path, constitution_path):
        import yaml

        findings_file = tmp_path / "spec_findings.yaml"
        adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="p-001",
            name="Persist test",
            description="desc",
            acceptance_criteria=["The system works correctly"],
            findings_path=findings_file,
            constitution_path=constitution_path,
        )
        assert findings_file.exists()
        data = yaml.safe_load(findings_file.read_text())
        assert "findings_by_hash" in data

    def test_missing_constitution_raises(self, tmp_path):
        from bob3.spec_quality.spec_critic import ConstitutionMissingError
        with pytest.raises(ConstitutionMissingError):
            adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
                feature_id="c-001",
                name="No constitution",
                description="desc",
                acceptance_criteria=["pytest: tests/test_x.py"],
                findings_path=tmp_path / "sf.yaml",
                constitution_path=tmp_path / "missing.md",
            )

    def test_defects_are_dicts_with_required_keys(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="d-001",
            name="Defect structure",
            description="desc",
            acceptance_criteria=["The module works correctly"],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        for defect in result["defects"]:
            assert isinstance(defect, dict)
            for key in ("feature_id", "ac_index", "defect_type", "rationale", "suggested_fix"):
                assert key in defect, f"defect missing key: {key}"

    def test_implementation_leak_defect(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="il-001",
            name="Impl leak",
            description="desc",
            acceptance_criteria=[
                "The system uses a hashmap for lookups",
                "pytest: tests/test_lookup_error.py",
            ],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        assert result["gate_passed"] is False
        defect_types = {d["defect_type"] for d in result["defects"]}
        assert "implementation_leak" in defect_types

    def test_gate_passed_is_false_when_defects_present(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="gf-001",
            name="Bad spec",
            description="desc",
            acceptance_criteria=["shall do something"],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        if result["defects"]:
            assert result["gate_passed"] is False
        else:
            assert result["gate_passed"] is True

    def test_gate_passed_is_bool(self, tmp_path, constitution_path):
        result = adversarial_spec_critic_sub_agent_gate_codegen_spec_quality(
            feature_id="gb-001",
            name="Bool check",
            description="desc",
            acceptance_criteria=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
            findings_path=tmp_path / "sf.yaml",
            constitution_path=constitution_path,
        )
        assert isinstance(result["gate_passed"], bool)

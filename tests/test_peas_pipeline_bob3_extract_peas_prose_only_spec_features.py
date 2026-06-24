"""Tests for peas_pipeline_bob3_extract_peas_prose_only_spec_features."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from bob3.peas_pipeline_bob3_extract_peas_prose_only_spec_features import (
    peas_pipeline_bob3_extract_peas_prose_only_spec_features,
)

# ---------------------------------------------------------------------------
# Shared fixture: mock the LLM synthesizer so tests don't make real API calls
# ---------------------------------------------------------------------------

FAKE_ACS = [
    "File exists: src/bob3/stub.py",
    "Function defined: stub.stub_fn",
    "behavior: handles the boundary case correctly",
]


def _fake_synthesizer():
    """Returns an async mock that stands in for spec_synthesizer.synthesize_for_feature."""
    return AsyncMock(return_value=FAKE_ACS)

SAMPLE_PEAS = textwrap.dedent(
    """\
    ## Cost Telemetry Enforcement
    Tier: Core  |  Priority: high  |  Slot: F-R7-100
    Tracks per-feature LLM API cost and enforces a hard budget ceiling.
    Agents that exceed the threshold are gracefully stopped.

    ## Liveness Probe
    Tier: Infra  |  Priority: medium  |  Slot: F-R7-101
    Periodic heartbeat check that verifies the orchestrator is still alive
    and restarts stuck sessions automatically.
    """
)

PROSE_ONLY_PEAS = textwrap.dedent(
    """\
    ## Auto Mint Feature
    Tracks events automatically without requiring operator YAML stubs.
    Each event is persisted to SQLite for durability.

    ## Secondary Feature
    Handles edge cases from the primary event flow, re-queuing on failure.
    """
)


def _make_peas_file(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "spec.md"
    p.write_text(content, encoding="utf-8")
    return p


class TestPeasPipelineFunction:
    def test_function_is_callable(self):
        assert callable(peas_pipeline_bob3_extract_peas_prose_only_spec_features)

    def test_returns_dict(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        assert isinstance(result, dict)

    def test_extracted_count_matches_features(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        assert result["extracted"] == 2

    def test_summary_has_required_keys(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        for key in ("extracted", "synthesized", "gate_passed", "gate_failed", "per_feature", "yaml_text"):
            assert key in result, f"Missing key: {key}"

    def test_yaml_text_is_valid_yaml(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        parsed = yaml.safe_load(result["yaml_text"])
        assert isinstance(parsed, dict)
        assert "features" in parsed

    def test_yaml_contains_feature_entries(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        parsed = yaml.safe_load(result["yaml_text"])
        assert len(parsed["features"]) == 2

    def test_slots_preserved_from_markdown(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        parsed = yaml.safe_load(result["yaml_text"])
        keys = [f["key"] for f in parsed["features"]]
        assert "F-R7-100" in keys
        assert "F-R7-101" in keys

    def test_prose_only_auto_mints_slots(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, PROSE_ONLY_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        parsed = yaml.safe_load(result["yaml_text"])
        for feature in parsed["features"]:
            assert "key" in feature
            assert feature["key"].startswith("F-R7-")

    def test_write_to_out_path(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        out_path = tmp_path / "out.yaml"
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path, out_path=out_path)
        assert out_path.exists()
        content = yaml.safe_load(out_path.read_text())
        assert "features" in content

    def test_per_feature_list_length_matches_extracted(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        assert len(result["per_feature"]) == result["extracted"]

    def test_gate_counts_sum_to_extracted(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        assert result["gate_passed"] + result["gate_failed"] == result["extracted"]

    def test_feature_titles_preserved(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        parsed = yaml.safe_load(result["yaml_text"])
        titles = {f["title"] for f in parsed["features"]}
        assert "Cost Telemetry Enforcement" in titles
        assert "Liveness Probe" in titles

    def test_empty_peas_returns_zero_extracted(self, tmp_path):
        peas_path = _make_peas_file(tmp_path, "")
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        assert result["extracted"] == 0
        assert result["synthesized"] == 0

    def test_empty_peas_returns_empty_features_yaml(self, tmp_path):
        """AC boundary: zero features → well-defined result, not a crash."""
        peas_path = _make_peas_file(tmp_path, "")
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        parsed = yaml.safe_load(result["yaml_text"])
        assert isinstance(parsed, dict)
        assert parsed.get("features") == []

    def test_whitespace_only_peas_is_well_defined(self, tmp_path):
        """AC boundary: whitespace-only input → zero extracted, no crash."""
        peas_path = _make_peas_file(tmp_path, "   \n\n   \n")
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)
        assert result["extracted"] == 0
        assert result["gate_passed"] + result["gate_failed"] == 0

    def test_nonexistent_path_raises_value_error(self, tmp_path):
        """AC: invalid input (missing file) raises ValueError, not silently succeeds."""
        missing = tmp_path / "does_not_exist.md"
        with pytest.raises(ValueError, match="does not exist"):
            peas_pipeline_bob3_extract_peas_prose_only_spec_features(missing)

    def test_non_path_input_raises_value_error(self):
        """AC: invalid input (wrong type) raises ValueError."""
        with pytest.raises((ValueError, TypeError)):
            peas_pipeline_bob3_extract_peas_prose_only_spec_features(12345)  # type: ignore[arg-type]


def test_peas_pipeline_bob3_extract_peas_prose_only_spec_features(tmp_path):
    """AC test: function is importable, callable, returns correct summary dict."""
    peas_path = _make_peas_file(tmp_path, SAMPLE_PEAS)
    with patch("bob3.spec_synthesizer.synthesize_for_feature", new_callable=AsyncMock, return_value=FAKE_ACS):
        result = peas_pipeline_bob3_extract_peas_prose_only_spec_features(peas_path)

    assert isinstance(result, dict)
    assert result["extracted"] == 2
    assert "yaml_text" in result
    assert "per_feature" in result

    parsed_yaml = yaml.safe_load(result["yaml_text"])
    assert "features" in parsed_yaml
    assert len(parsed_yaml["features"]) == 2
    keys = [f["key"] for f in parsed_yaml["features"]]
    assert "F-R7-100" in keys
    assert "F-R7-101" in keys

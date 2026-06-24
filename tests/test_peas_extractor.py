"""Tests for bob3.peas_extractor.extract_from_peas.

AC: pytest: tests/test_peas_extractor.py
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from bob3.peas_extractor import extract_from_peas


async def _stub_synthesize(**kwargs: Any) -> list[str]:
    """Stub synthesizer for tests — avoids LLM calls."""
    title = kwargs.get("title", "Feature")
    return [
        f"File exists: src/bob3/{title.lower().replace(' ', '_')}.py",
        f"pytest: tests/test_{title.lower().replace(' ', '_')}.py",
        "boundary: empty input returns well-defined result",
        "error: invalid input raises ValueError",
    ]


class TestExtractFromPeasBasic:
    """Basic correctness tests for extract_from_peas."""

    def test_returns_dict_with_required_keys(self, tmp_path):
        peas = tmp_path / "spec.md"
        peas.write_text(
            "## Widget\nTier: Core  |  Priority: high  |  Slot: F-R7-001\nWidget desc.\n",
            encoding="utf-8",
        )
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        for key in ("extracted", "synthesized", "gate_passed", "gate_failed", "per_feature", "yaml_text"):
            assert key in result, f"Missing key: {key}"

    def test_extracted_count_matches_headings(self, tmp_path):
        peas = tmp_path / "two.md"
        peas.write_text(
            textwrap.dedent("""\
            ## Alpha
            Tier: Core  |  Priority: high  |  Slot: F-R7-010
            Alpha description.

            ## Beta
            Tier: Infra  |  Priority: low  |  Slot: F-R7-011
            Beta description.
            """),
            encoding="utf-8",
        )
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        assert result["extracted"] == 2

    def test_yaml_text_is_valid_yaml(self, tmp_path):
        peas = tmp_path / "valid.md"
        peas.write_text(
            "## Feature A\nTier: Core  |  Priority: medium  |  Slot: F-R7-020\nDesc A.\n",
            encoding="utf-8",
        )
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        parsed = yaml.safe_load(result["yaml_text"])
        assert isinstance(parsed, dict)
        assert "features" in parsed

    def test_feature_keys_present_in_output_yaml(self, tmp_path):
        peas = tmp_path / "keys.md"
        peas.write_text(
            "## Key Feature\nTier: Core  |  Priority: high  |  Slot: F-R7-030\nDesc.\n",
            encoding="utf-8",
        )
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        parsed = yaml.safe_load(result["yaml_text"])
        keys = [f["key"] for f in parsed["features"]]
        assert "F-R7-030" in keys

    def test_auto_mint_slot_when_missing(self, tmp_path):
        peas = tmp_path / "noslot.md"
        peas.write_text(
            "## Unslotted\nTier: Core  |  Priority: medium\nDesc without slot.\n",
            encoding="utf-8",
        )
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        parsed = yaml.safe_load(result["yaml_text"])
        assert parsed["features"][0]["key"].startswith("F-R7-")

    def test_out_path_written_when_provided(self, tmp_path):
        peas = tmp_path / "out.md"
        peas.write_text(
            "## Outbound\nTier: Core  |  Priority: high  |  Slot: F-R7-040\nDesc.\n",
            encoding="utf-8",
        )
        out = tmp_path / "result.yaml"
        extract_from_peas(peas, out_path=out, _synthesize_fn=_stub_synthesize)
        assert out.exists()
        content = yaml.safe_load(out.read_text())
        assert "features" in content

    def test_gate_counts_sum_to_extracted(self, tmp_path):
        peas = tmp_path / "gate.md"
        peas.write_text(
            textwrap.dedent("""\
            ## Feat1
            Tier: Core  |  Priority: high  |  Slot: F-R7-050
            Desc1.

            ## Feat2
            Tier: Infra  |  Priority: low  |  Slot: F-R7-051
            Desc2.
            """),
            encoding="utf-8",
        )
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        assert result["gate_passed"] + result["gate_failed"] == result["extracted"]

    def test_per_feature_list_has_correct_length(self, tmp_path):
        peas = tmp_path / "pf.md"
        peas.write_text(
            textwrap.dedent("""\
            ## FeatureX
            Tier: Core  |  Priority: medium  |  Slot: F-R7-060
            DescX.

            ## FeatureY
            Tier: Core  |  Priority: medium  |  Slot: F-R7-061
            DescY.

            ## FeatureZ
            Tier: Core  |  Priority: medium  |  Slot: F-R7-062
            DescZ.
            """),
            encoding="utf-8",
        )
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        assert len(result["per_feature"]) == 3


class TestExtractFromPeasErrors:
    """Error-path tests — ensure ValueError is raised, not silent failures."""

    def test_missing_file_raises_value_error(self, tmp_path):
        missing = tmp_path / "no_file.md"
        with pytest.raises(ValueError, match="does not exist"):
            extract_from_peas(missing)

    def test_non_path_integer_raises(self):
        with pytest.raises((ValueError, TypeError)):
            extract_from_peas(42)  # type: ignore[arg-type]

    def test_non_path_none_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            extract_from_peas(None)  # type: ignore[arg-type]

    def test_missing_file_does_not_silently_succeed(self, tmp_path):
        missing = tmp_path / "ghost.md"
        raised = False
        try:
            extract_from_peas(missing)
        except (ValueError, TypeError, FileNotFoundError):
            raised = True
        assert raised, "Expected an exception but got a result"


class TestExtractFromPeasBoundary:
    """Boundary tests — edge inputs return well-defined results."""

    def test_empty_file_returns_zero_extracted(self, tmp_path):
        peas = tmp_path / "empty.md"
        peas.write_text("", encoding="utf-8")
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        assert result["extracted"] == 0

    def test_empty_file_yields_valid_yaml(self, tmp_path):
        peas = tmp_path / "empty2.md"
        peas.write_text("", encoding="utf-8")
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        parsed = yaml.safe_load(result["yaml_text"])
        assert isinstance(parsed, dict)

    def test_single_heading_no_body(self, tmp_path):
        peas = tmp_path / "bare.md"
        peas.write_text("## Bare\n", encoding="utf-8")
        result = extract_from_peas(peas, _synthesize_fn=_stub_synthesize)
        assert result["extracted"] == 1

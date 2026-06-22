"""Boundary tests for the PEAS pipeline.

AC: empty, zero, or minimum input returns a well-defined result rather than raising.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from bob3.extract_from_peas import (
    emit_stub_features,
    extract_and_synthesize,
    parse_peas_markdown,
)


async def _fast_synthesize(**kwargs: Any) -> list[str]:
    """Fast stub synthesizer for tests — returns deterministic ACs without LLM calls."""
    title = kwargs.get("title", "Feature")
    return [
        f"File exists: src/bob3/{title.lower().replace(' ', '_')}.py",
        f"pytest: tests/test_{title.lower().replace(' ', '_')}.py",
        "boundary: empty input returns well-defined result",
        "error: invalid input raises ValueError",
    ]


# ---------------------------------------------------------------------------
# parse_peas_markdown boundary cases
# ---------------------------------------------------------------------------


class TestParseBoundary:
    def test_empty_string(self):
        result = parse_peas_markdown("")
        assert result == []

    def test_whitespace_only(self):
        result = parse_peas_markdown("   \n\n\t\n")
        assert result == []

    def test_no_headings(self):
        result = parse_peas_markdown("Just some prose with no markdown headings.\n")
        assert result == []

    def test_single_heading_no_body(self):
        result = parse_peas_markdown("## Minimal Feature\n")
        assert len(result) == 1
        assert result[0]["title"] == "Minimal Feature"
        assert result[0]["description"] == ""

    def test_single_heading_with_metadata_only(self):
        result = parse_peas_markdown("## Edge Case\nTier: Core  |  Priority: low\n")
        assert len(result) == 1
        assert result[0]["tier"] == "Core"
        assert result[0]["priority"] == "low"
        assert result[0]["description"] == ""

    def test_preamble_before_first_heading_ignored(self):
        text = "Preamble text ignored.\n\n## Real Feature\nTier: Core  |  Priority: high\nDesc.\n"
        result = parse_peas_markdown(text)
        assert len(result) == 1
        assert result[0]["title"] == "Real Feature"

    def test_defaults_applied_when_metadata_absent(self):
        result = parse_peas_markdown("## Bare Feature\nDescription only.\n")
        assert result[0]["tier"] == "Core"
        assert result[0]["priority"] == "medium"
        assert result[0]["slot"] is None

    def test_single_character_title(self):
        result = parse_peas_markdown("## X\nTier: Core  |  Priority: high\nDesc.\n")
        assert len(result) == 1
        assert result[0]["title"] == "X"


# ---------------------------------------------------------------------------
# emit_stub_features boundary cases
# ---------------------------------------------------------------------------


class TestEmitStubBoundary:
    def test_empty_list_returns_empty(self):
        assert emit_stub_features([]) == []

    def test_single_feature_minimum_fields(self):
        parsed = [{"title": "A", "tier": "Core", "priority": "high", "slot": None, "description": "", "permanent_forward_carry": False}]
        stubs = emit_stub_features(parsed)
        assert len(stubs) == 1
        assert stubs[0]["key"].startswith("F-R7-")

    def test_no_collision_with_existing_slots(self):
        parsed = [
            {"title": "A", "tier": "Core", "priority": "high", "slot": None, "description": "", "permanent_forward_carry": False},
            {"title": "B", "tier": "Core", "priority": "low", "slot": None, "description": "", "permanent_forward_carry": False},
        ]
        existing = {"F-R7-001", "F-R7-002", "F-R7-003"}
        stubs = emit_stub_features(parsed, existing_slots=existing)
        for stub in stubs:
            assert stub["key"] not in existing

    def test_all_keys_unique_for_slotless_batch(self):
        parsed = [
            {"title": f"Feature {i}", "tier": "Core", "priority": "medium", "slot": None, "description": f"Desc {i}", "permanent_forward_carry": False}
            for i in range(5)
        ]
        stubs = emit_stub_features(parsed)
        keys = [s["key"] for s in stubs]
        assert len(keys) == len(set(keys))

    def test_tbd_placeholder_set_for_every_stub(self):
        parsed = [{"title": "Feat", "tier": "Core", "priority": "low", "slot": "F-R7-010", "description": "Desc.", "permanent_forward_carry": False}]
        stubs = emit_stub_features(parsed)
        ac = stubs[0]["acceptance_criteria"]
        assert isinstance(ac, list)
        assert len(ac) >= 1
        assert any("TBD" in item for item in ac)

    def test_yaml_roundtrip_with_empty_description(self):
        parsed = [{"title": "Empty Desc", "tier": "Core", "priority": "medium", "slot": "F-R7-050", "description": "", "permanent_forward_carry": False}]
        stubs = emit_stub_features(parsed)
        output = {"features": stubs}
        yaml_text = yaml.safe_dump(output, sort_keys=False)
        reloaded = yaml.safe_load(yaml_text)
        assert reloaded["features"][0]["key"] == "F-R7-050"


# ---------------------------------------------------------------------------
# extract_and_synthesize boundary cases — well-defined results, no raises
# ---------------------------------------------------------------------------


class TestExtractAndSynthesizeBoundary:
    def test_empty_peas_file_returns_zero_extracted(self, tmp_path):
        peas = tmp_path / "empty.md"
        peas.write_text("", encoding="utf-8")
        result = extract_and_synthesize(peas, _synthesize_fn=_fast_synthesize)
        assert result["extracted"] == 0
        assert result["synthesized"] == 0

    def test_empty_peas_file_returns_valid_yaml(self, tmp_path):
        peas = tmp_path / "empty.md"
        peas.write_text("", encoding="utf-8")
        result = extract_and_synthesize(peas, _synthesize_fn=_fast_synthesize)
        parsed = yaml.safe_load(result["yaml_text"])
        assert isinstance(parsed, dict)
        assert parsed.get("features") == []

    def test_whitespace_only_peas_is_well_defined(self, tmp_path):
        peas = tmp_path / "ws.md"
        peas.write_text("   \n\n   \n", encoding="utf-8")
        result = extract_and_synthesize(peas, _synthesize_fn=_fast_synthesize)
        assert result["extracted"] == 0
        assert result["gate_passed"] + result["gate_failed"] == 0

    def test_single_minimal_feature(self, tmp_path):
        peas = tmp_path / "min.md"
        peas.write_text("## Solo\nTier: Core  |  Priority: high  |  Slot: F-R7-001\nOne line.\n", encoding="utf-8")
        result = extract_and_synthesize(peas, _synthesize_fn=_fast_synthesize)
        assert result["extracted"] == 1
        parsed = yaml.safe_load(result["yaml_text"])
        assert len(parsed["features"]) == 1

    def test_no_slot_feature_auto_mints_key(self, tmp_path):
        peas = tmp_path / "noslot.md"
        peas.write_text("## Unlabeled\nTier: Core  |  Priority: medium\nDesc.\n", encoding="utf-8")
        result = extract_and_synthesize(peas, _synthesize_fn=_fast_synthesize)
        parsed = yaml.safe_load(result["yaml_text"])
        assert parsed["features"][0]["key"].startswith("F-R7-")

    def test_gate_counts_sum_to_extracted(self, tmp_path):
        peas = tmp_path / "two.md"
        peas.write_text(
            textwrap.dedent("""\
            ## Alpha
            Tier: Core  |  Priority: high  |  Slot: F-R7-100
            Alpha description.

            ## Beta
            Tier: Infra  |  Priority: low  |  Slot: F-R7-101
            Beta description.
            """),
            encoding="utf-8",
        )
        result = extract_and_synthesize(peas, _synthesize_fn=_fast_synthesize)
        assert result["gate_passed"] + result["gate_failed"] == result["extracted"]

    def test_out_path_written_when_given(self, tmp_path):
        peas = tmp_path / "spec.md"
        peas.write_text("## Feature\nTier: Core  |  Priority: high  |  Slot: F-R7-005\nDesc.\n", encoding="utf-8")
        out = tmp_path / "out.yaml"
        result = extract_and_synthesize(peas, out_path=out, _synthesize_fn=_fast_synthesize)
        assert out.exists()
        content = yaml.safe_load(out.read_text())
        assert "features" in content

    def test_summary_has_all_required_keys(self, tmp_path):
        peas = tmp_path / "check.md"
        peas.write_text("## Check\nTier: Core  |  Priority: medium  |  Slot: F-R7-010\nBody.\n", encoding="utf-8")
        result = extract_and_synthesize(peas, _synthesize_fn=_fast_synthesize)
        for key in ("extracted", "synthesized", "gate_passed", "gate_failed", "per_feature", "yaml_text"):
            assert key in result

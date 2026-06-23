"""Boundary tests for bob3.extract_from_peas — edge and minimum input cases."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bob3.extract_from_peas import (
    emit_stub_features,
    mint_feature_key,
    parse_peas_markdown,
    run_extraction_pipeline,
    TBD_PLACEHOLDER,
)


class TestParsePeasMarkdownBoundary:
    def test_empty_string_returns_empty(self):
        assert parse_peas_markdown("") == []

    def test_whitespace_only_returns_empty(self):
        assert parse_peas_markdown("   \n\n  \t  ") == []

    def test_no_headings_returns_empty(self):
        result = parse_peas_markdown("some prose without any headings")
        assert result == []

    def test_single_heading_no_body(self):
        result = parse_peas_markdown("## Lone Heading")
        assert len(result) == 1
        assert result[0]["title"] == "Lone Heading"
        assert result[0]["description"] == ""

    def test_heading_only_whitespace_body(self):
        result = parse_peas_markdown("## Heading\n   \n  ")
        assert len(result) == 1
        assert result[0]["description"] == ""

    def test_minimum_feature_has_defaults(self):
        result = parse_peas_markdown("## Minimal")
        assert result[0]["tier"] == "Core"
        assert result[0]["priority"] == "medium"
        assert result[0]["slot"] is None

    def test_single_character_title(self):
        result = parse_peas_markdown("## X\nSome description.")
        assert result[0]["title"] == "X"

    def test_preamble_before_first_heading_ignored(self):
        text = "# Intro\nThis is preamble text.\n## Real Feature\nDescription here."
        result = parse_peas_markdown(text)
        assert len(result) == 1
        assert result[0]["title"] == "Real Feature"


class TestEmitStubBoundary:
    def test_empty_list_returns_empty(self):
        assert emit_stub_features([]) == []

    def test_single_feature_minimum_fields(self):
        parsed = [{"title": "T", "tier": "Core", "priority": "medium", "slot": "F-R7-001", "permanent_forward_carry": False, "description": ""}]
        stubs = emit_stub_features(parsed)
        assert len(stubs) == 1
        assert stubs[0]["key"] == "F-R7-001"

    def test_auto_mint_when_no_slot(self):
        parsed = [{"title": "T", "tier": "Core", "priority": "medium", "slot": None, "permanent_forward_carry": False, "description": ""}]
        stubs = emit_stub_features(parsed)
        assert stubs[0]["key"].startswith("F-R7-")

    def test_no_collision_with_existing_slots(self):
        parsed = [{"title": "T", "tier": "Core", "priority": "medium", "slot": None, "permanent_forward_carry": False, "description": ""}]
        stubs = emit_stub_features(parsed, existing_slots={"F-R7-001"})
        assert stubs[0]["key"] != "F-R7-001"

    def test_all_keys_unique_for_slotless_batch(self):
        parsed = [
            {"title": f"F{i}", "tier": "Core", "priority": "medium", "slot": None, "permanent_forward_carry": False, "description": ""}
            for i in range(5)
        ]
        stubs = emit_stub_features(parsed)
        keys = [s["key"] for s in stubs]
        assert len(keys) == len(set(keys))

    def test_tbd_placeholder_set_for_every_stub(self):
        parsed = [{"title": "T", "tier": "Core", "priority": "medium", "slot": "F-R7-001", "permanent_forward_carry": False, "description": "desc"}]
        stubs = emit_stub_features(parsed)
        assert stubs[0]["acceptance_criteria"] == [TBD_PLACEHOLDER]


class TestMintFeatureKeyBoundary:
    def test_empty_set_returns_first(self):
        key = mint_feature_key(set())
        assert key == "F-R7-001"

    def test_none_treated_as_empty(self):
        key = mint_feature_key(None)
        assert key == "F-R7-001"

    def test_skips_occupied_slot(self):
        key = mint_feature_key({"F-R7-001"})
        assert key == "F-R7-002"

    def test_fills_gap(self):
        key = mint_feature_key({"F-R7-001", "F-R7-003"})
        assert key == "F-R7-002"

    def test_non_r7_slots_ignored(self):
        key = mint_feature_key({"F-R1-001", "F-R2-001"})
        assert key == "F-R7-001"


class TestRunExtractionPipelineBoundary:
    def test_empty_peas_file_returns_zero_extracted(self, tmp_path):
        peas = tmp_path / "empty.md"
        peas.write_text("", encoding="utf-8")

        async def _stub(**kw):
            return ["AC1"]

        result = run_extraction_pipeline(peas, _synthesize_fn=_stub)
        assert result["extracted"] == 0

    def test_empty_peas_returns_valid_yaml(self, tmp_path):
        import yaml
        peas = tmp_path / "empty.md"
        peas.write_text("", encoding="utf-8")

        async def _stub(**kw):
            return ["AC1"]

        result = run_extraction_pipeline(peas, _synthesize_fn=_stub)
        parsed = yaml.safe_load(result["yaml_text"])
        assert isinstance(parsed, dict)
        assert "features" in parsed

    def test_whitespace_only_file_is_well_defined(self, tmp_path):
        peas = tmp_path / "ws.md"
        peas.write_text("   \n\n\t\n", encoding="utf-8")

        async def _stub(**kw):
            return ["AC1"]

        result = run_extraction_pipeline(peas, _synthesize_fn=_stub)
        assert result["extracted"] == 0

    def test_single_minimal_feature(self, tmp_path):
        peas = tmp_path / "single.md"
        peas.write_text("## Only Feature\nDoes one thing.", encoding="utf-8")

        async def _stub(**kw):
            return ["AC single"]

        result = run_extraction_pipeline(peas, _synthesize_fn=_stub)
        assert result["extracted"] == 1
        assert result["gate_passed"] + result["gate_failed"] == 1

    def test_summary_has_all_required_keys(self, tmp_path):
        peas = tmp_path / "feat.md"
        peas.write_text("## A\nDesc.", encoding="utf-8")

        async def _stub(**kw):
            return ["AC x"]

        result = run_extraction_pipeline(peas, _synthesize_fn=_stub)
        for key in ("extracted", "synthesized", "gate_passed", "gate_failed", "per_feature", "yaml_text"):
            assert key in result

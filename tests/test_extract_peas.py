"""Tests for bob3.extract_peas — verifies the public PEAS API module.

These tests confirm that:
- ``bob3.extract_peas`` is importable.
- ``parse_peas_markdown`` is a callable and produces correct output.
- ``synthesize_features`` is a callable and processes stub feature dicts.
- The module exports are a strict superset of the required AC symbols.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

import bob3.extract_peas as _mod
from bob3.extract_peas import parse_peas_markdown, synthesize_features


# ---------------------------------------------------------------------------
# Module-level symbol checks
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_parse_peas_markdown_callable(self):
        assert callable(parse_peas_markdown)

    def test_synthesize_features_callable(self):
        assert callable(synthesize_features)

    def test_module_has_emit_stub_features(self):
        assert hasattr(_mod, "emit_stub_features")

    def test_module_has_extract_and_synthesize(self):
        assert hasattr(_mod, "extract_and_synthesize")

    def test_module_has_run_pipeline(self):
        assert hasattr(_mod, "run_pipeline")

    def test_module_has_tbd_placeholder(self):
        assert hasattr(_mod, "TBD_PLACEHOLDER")
        assert "TBD" in _mod.TBD_PLACEHOLDER


# ---------------------------------------------------------------------------
# parse_peas_markdown correctness
# ---------------------------------------------------------------------------


SIMPLE_PEAS = textwrap.dedent(
    """\
    ## Alpha Feature
    Tier: Core  |  Priority: high  |  Slot: F-R7-200
    First feature description.

    ## Beta Feature
    Tier: Infra  |  Priority: low  |  Slot: F-R7-201
    Second feature description.
    """
)


class TestParsePeasMarkdown:
    def test_returns_list(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        assert isinstance(result, list)

    def test_correct_count(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        assert len(result) == 2

    def test_title_extracted(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        assert result[0]["title"] == "Alpha Feature"
        assert result[1]["title"] == "Beta Feature"

    def test_tier_extracted(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        assert result[0]["tier"] == "Core"
        assert result[1]["tier"] == "Infra"

    def test_priority_extracted(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        assert result[0]["priority"] == "high"
        assert result[1]["priority"] == "low"

    def test_slot_extracted(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        assert result[0]["slot"] == "F-R7-200"
        assert result[1]["slot"] == "F-R7-201"

    def test_description_extracted(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        assert "First feature" in result[0]["description"]
        assert "Second feature" in result[1]["description"]

    def test_empty_string_returns_empty_list(self):
        assert parse_peas_markdown("") == []

    def test_no_headings_returns_empty_list(self):
        assert parse_peas_markdown("Just prose, no headings.") == []

    def test_defaults_when_metadata_absent(self):
        text = "## Bare Feature\nOnly description, no metadata.\n"
        result = parse_peas_markdown(text)
        assert result[0]["tier"] == "Core"
        assert result[0]["priority"] == "medium"
        assert result[0]["slot"] is None

    def test_preamble_ignored(self):
        text = "Preamble ignored.\n\n## Real Feature\nTier: Core  |  Priority: medium\nBody.\n"
        result = parse_peas_markdown(text)
        assert len(result) == 1
        assert result[0]["title"] == "Real Feature"

    def test_result_dicts_have_required_keys(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        required = {"title", "tier", "priority", "slot", "description"}
        for feature in result:
            assert required.issubset(feature.keys())


# ---------------------------------------------------------------------------
# synthesize_features correctness
# ---------------------------------------------------------------------------


async def _stub_synthesizer(**kwargs: Any) -> list[str]:
    """Deterministic async synthesizer for tests — no LLM calls."""
    title = kwargs.get("title", "Feature")
    return [
        f"File exists: src/bob3/{title.lower().replace(' ', '_')}.py",
        f"pytest: tests/test_{title.lower().replace(' ', '_')}.py",
    ]


class TestSynthesizeFeatures:
    def test_returns_list(self):
        stubs = [
            {
                "key": "F-R7-300",
                "title": "Gamma",
                "description": "Gamma description.",
                "acceptance_criteria": [_mod.TBD_PLACEHOLDER],
            }
        ]
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesizer)
        assert isinstance(result, list)

    def test_tbd_replaced_with_real_criteria(self):
        stubs = [
            {
                "key": "F-R7-301",
                "title": "Delta",
                "description": "Delta description.",
                "acceptance_criteria": [_mod.TBD_PLACEHOLDER],
            }
        ]
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesizer)
        ac = result[0]["acceptance_criteria"]
        assert not any(_mod.TBD_PLACEHOLDER in item for item in ac)

    def test_non_tbd_criteria_left_unchanged(self):
        original_ac = ["File exists: src/bob3/existing.py", "pytest: tests/test_existing.py"]
        stubs = [
            {
                "key": "F-R7-302",
                "title": "Existing",
                "description": "Has real ACs already.",
                "acceptance_criteria": original_ac,
            }
        ]
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesizer)
        assert result[0]["acceptance_criteria"] == original_ac

    def test_empty_stubs_list_returns_empty(self):
        result = synthesize_features([], _synthesize_fn=_stub_synthesizer)
        assert result == []

    def test_modifies_stubs_in_place_and_returns_them(self):
        stubs = [
            {
                "key": "F-R7-303",
                "title": "Epsilon",
                "description": "Epsilon description.",
                "acceptance_criteria": [_mod.TBD_PLACEHOLDER],
            }
        ]
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesizer)
        assert result is stubs

    def test_multiple_stubs_all_synthesized(self):
        stubs = [
            {
                "key": f"F-R7-{400 + i}",
                "title": f"Feature {i}",
                "description": f"Description {i}.",
                "acceptance_criteria": [_mod.TBD_PLACEHOLDER],
            }
            for i in range(3)
        ]
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesizer)
        for stub in result:
            assert not any(_mod.TBD_PLACEHOLDER in item for item in stub["acceptance_criteria"])


# ---------------------------------------------------------------------------
# Integration: parse → synthesize round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_parse_then_synthesize_produces_valid_yaml(self):
        text = textwrap.dedent(
            """\
            ## Widget Builder
            Tier: Core  |  Priority: high  |  Slot: F-R7-500
            Builds widgets from configuration files.
            """
        )
        from bob3.extract_peas import emit_stub_features

        parsed = parse_peas_markdown(text)
        stubs = emit_stub_features(parsed)
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesizer)

        output = yaml.safe_dump({"features": result}, sort_keys=False)
        reloaded = yaml.safe_load(output)

        assert "features" in reloaded
        assert len(reloaded["features"]) == 1
        feature = reloaded["features"][0]
        assert feature["key"] == "F-R7-500"
        assert isinstance(feature["acceptance_criteria"], list)
        assert len(feature["acceptance_criteria"]) > 0

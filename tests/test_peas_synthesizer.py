"""Tests for bob.peas_synthesizer — the canonical PEAS pipeline module.

Verifies that parse_peas_markdown and synthesize_features are importable
from bob.peas_synthesizer and behave correctly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from bob.peas_synthesizer import (
    parse_peas_markdown,
    synthesize_features,
    emit_stub_features,
    TBD_PLACEHOLDER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _stub_synthesize(**kwargs: Any) -> list[str]:
    """Fast stub synthesizer — no LLM call, deterministic output."""
    title = kwargs.get("title", "Feature")
    return [
        f"File exists: src/bob/{title.lower().replace(' ', '_')}.py",
        f"pytest: tests/test_{title.lower().replace(' ', '_')}.py",
        "boundary: empty input returns well-defined result",
        "error: invalid input raises ValueError",
    ]


# ---------------------------------------------------------------------------
# parse_peas_markdown
# ---------------------------------------------------------------------------


class TestParsePeasMarkdown:
    def test_importable_from_peas_synthesizer(self):
        from bob.peas_synthesizer import parse_peas_markdown as fn
        assert callable(fn)

    def test_empty_string_returns_empty_list(self):
        result = parse_peas_markdown("")
        assert result == []

    def test_single_feature_basic(self):
        md = "## My Feature\nTier: Core  |  Priority: high\nA description.\n"
        result = parse_peas_markdown(md)
        assert len(result) == 1
        assert result[0]["title"] == "My Feature"
        assert result[0]["tier"] == "Core"
        assert result[0]["priority"] == "high"
        assert "A description." in result[0]["description"]

    def test_single_feature_with_slot(self):
        md = "## Slotted\nTier: Infra  |  Priority: low  |  Slot: F-R7-042\nDesc.\n"
        result = parse_peas_markdown(md)
        assert result[0]["slot"] == "F-R7-042"

    def test_defaults_when_no_metadata(self):
        result = parse_peas_markdown("## Bare Feature\nBody text.\n")
        assert result[0]["tier"] == "Core"
        assert result[0]["priority"] == "medium"
        assert result[0]["slot"] is None

    def test_multiple_features(self):
        md = (
            "## Alpha\nTier: Core  |  Priority: high\nAlpha desc.\n\n"
            "## Beta\nTier: Infra  |  Priority: low\nBeta desc.\n"
        )
        result = parse_peas_markdown(md)
        assert len(result) == 2
        assert result[0]["title"] == "Alpha"
        assert result[1]["title"] == "Beta"

    def test_preamble_before_heading_ignored(self):
        md = "Intro text.\n\n## Feature\nTier: Core  |  Priority: high\nDesc.\n"
        result = parse_peas_markdown(md)
        assert len(result) == 1
        assert result[0]["title"] == "Feature"

    def test_permanent_forward_carry_false_by_default(self):
        result = parse_peas_markdown("## F\nTier: Core  |  Priority: high\nDesc.\n")
        assert result[0]["permanent_forward_carry"] is False

    def test_permanent_forward_carry_parsed_true(self):
        md = "## F\nTier: Core  |  Priority: high  |  PermanentForwardCarry: true\nDesc.\n"
        result = parse_peas_markdown(md)
        assert result[0]["permanent_forward_carry"] is True


# ---------------------------------------------------------------------------
# synthesize_features
# ---------------------------------------------------------------------------


class TestSynthesizeFeatures:
    def test_importable_from_peas_synthesizer(self):
        from bob.peas_synthesizer import synthesize_features as fn
        assert callable(fn)

    def test_empty_list_returns_empty(self):
        result = synthesize_features([], _synthesize_fn=_stub_synthesize)
        assert result == []

    def test_tbd_placeholder_replaced(self):
        stubs = [
            {
                "key": "F-R7-001",
                "title": "Test Feature",
                "tier": "Core",
                "priority": "high",
                "description": "A test feature.",
                "acceptance_criteria": [TBD_PLACEHOLDER],
            }
        ]
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesize)
        assert len(result) == 1
        ac = result[0]["acceptance_criteria"]
        assert isinstance(ac, list)
        assert len(ac) > 0
        assert not any(TBD_PLACEHOLDER in item for item in ac)

    def test_existing_real_acs_unchanged(self):
        real_ac = ["File exists: src/bob/mymodule.py", "pytest: tests/test_mymodule.py"]
        stubs = [
            {
                "key": "F-R7-002",
                "title": "Existing Feature",
                "tier": "Core",
                "priority": "medium",
                "description": "Already has criteria.",
                "acceptance_criteria": real_ac,
            }
        ]
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesize)
        assert result[0]["acceptance_criteria"] == real_ac

    def test_returns_same_list_object(self):
        stubs = [
            {
                "key": "F-R7-003",
                "title": "Mutated",
                "tier": "Core",
                "priority": "high",
                "description": "In-place update.",
                "acceptance_criteria": [TBD_PLACEHOLDER],
            }
        ]
        returned = synthesize_features(stubs, _synthesize_fn=_stub_synthesize)
        assert returned is stubs

    def test_multiple_stubs_all_synthesized(self):
        stubs = [
            {
                "key": f"F-R7-{i:03d}",
                "title": f"Feature {i}",
                "tier": "Core",
                "priority": "medium",
                "description": f"Description {i}.",
                "acceptance_criteria": [TBD_PLACEHOLDER],
            }
            for i in range(3)
        ]
        result = synthesize_features(stubs, _synthesize_fn=_stub_synthesize)
        for stub in result:
            assert not any(TBD_PLACEHOLDER in item for item in stub["acceptance_criteria"])


# ---------------------------------------------------------------------------
# Integration: parse + emit stubs + synthesize
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_parse_emit_synthesize_roundtrip(self):
        md = (
            "## Parser Feature\nTier: Core  |  Priority: high  |  Slot: F-R7-200\n"
            "Implements PEAS parsing.\n\n"
            "## Synthesizer Feature\nTier: Core  |  Priority: medium  |  Slot: F-R7-201\n"
            "Fills in TBD acceptance criteria.\n"
        )
        parsed = parse_peas_markdown(md)
        assert len(parsed) == 2

        stubs = emit_stub_features(parsed)
        assert len(stubs) == 2
        assert all(TBD_PLACEHOLDER in s["acceptance_criteria"][0] for s in stubs)

        synthesized = synthesize_features(stubs, _synthesize_fn=_stub_synthesize)
        assert len(synthesized) == 2
        for stub in synthesized:
            assert stub["acceptance_criteria"]
            assert not any(TBD_PLACEHOLDER in ac for ac in stub["acceptance_criteria"])

    def test_yaml_output_is_valid(self):
        md = "## Valid Feature\nTier: Core  |  Priority: high  |  Slot: F-R7-300\nDesc.\n"
        parsed = parse_peas_markdown(md)
        stubs = emit_stub_features(parsed)
        synthesized = synthesize_features(stubs, _synthesize_fn=_stub_synthesize)

        output = {"features": synthesized}
        yaml_text = yaml.safe_dump(output, sort_keys=False)
        reloaded = yaml.safe_load(yaml_text)
        assert "features" in reloaded
        assert reloaded["features"][0]["key"] == "F-R7-300"

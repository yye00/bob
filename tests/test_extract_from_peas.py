"""Tests for bob3.extract_from_peas — PEAS pipeline."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from bob3.extract_from_peas import (
    emit_stub_features,
    parse_peas_markdown,
    TBD_PLACEHOLDER,
    _next_slot,
)


# ---------------------------------------------------------------------------
# parse_peas_markdown
# ---------------------------------------------------------------------------


SIMPLE_PEAS = textwrap.dedent(
    """\
    ## My Feature
    Tier: Core  |  Priority: high  |  Slot: F-R7-042
    This feature does something useful.

    ## Another Feature
    Tier: Infra  |  Priority: low  |  Slot: F-R7-043
    A second feature description here.
    """
)

NO_SLOT_PEAS = textwrap.dedent(
    """\
    ## Unnamed Feature
    Tier: Core  |  Priority: medium
    Description without a slot.
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
        assert result[0]["title"] == "My Feature"
        assert result[1]["title"] == "Another Feature"

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
        assert result[0]["slot"] == "F-R7-042"
        assert result[1]["slot"] == "F-R7-043"

    def test_description_extracted(self):
        result = parse_peas_markdown(SIMPLE_PEAS)
        assert "useful" in result[0]["description"]
        assert "second" in result[1]["description"]

    def test_no_slot_returns_none(self):
        result = parse_peas_markdown(NO_SLOT_PEAS)
        assert len(result) == 1
        assert result[0]["slot"] is None

    def test_empty_string_returns_empty(self):
        result = parse_peas_markdown("")
        assert result == []

    def test_content_before_first_heading_ignored(self):
        text = "Preamble text\n\n## First\nTier: Core  |  Priority: high\nBody.\n"
        result = parse_peas_markdown(text)
        assert len(result) == 1
        assert result[0]["title"] == "First"

    def test_single_feature_round_trip(self):
        text = "## Single\nTier: Edge  |  Priority: critical  |  Slot: F-R7-999\nOnly one.\n"
        result = parse_peas_markdown(text)
        assert result[0]["slot"] == "F-R7-999"
        assert result[0]["tier"] == "Edge"
        assert result[0]["priority"] == "critical"

    def test_default_tier_and_priority_when_absent(self):
        text = "## Bare Feature\nJust a description.\n"
        result = parse_peas_markdown(text)
        assert result[0]["tier"] == "Core"
        assert result[0]["priority"] == "medium"


# ---------------------------------------------------------------------------
# emit_stub_features
# ---------------------------------------------------------------------------


class TestEmitStubFeatures:
    def test_returns_list(self):
        parsed = parse_peas_markdown(SIMPLE_PEAS)
        stubs = emit_stub_features(parsed)
        assert isinstance(stubs, list)
        assert len(stubs) == 2

    def test_key_comes_from_slot(self):
        parsed = parse_peas_markdown(SIMPLE_PEAS)
        stubs = emit_stub_features(parsed)
        assert stubs[0]["key"] == "F-R7-042"
        assert stubs[1]["key"] == "F-R7-043"

    def test_tbd_placeholder_in_acceptance_criteria(self):
        parsed = parse_peas_markdown(SIMPLE_PEAS)
        stubs = emit_stub_features(parsed)
        for stub in stubs:
            ac = stub["acceptance_criteria"]
            assert isinstance(ac, list)
            assert any(TBD_PLACEHOLDER in item for item in ac)

    def test_auto_mint_slot_when_missing(self):
        parsed = parse_peas_markdown(NO_SLOT_PEAS)
        stubs = emit_stub_features(parsed)
        assert len(stubs) == 1
        key = stubs[0]["key"]
        assert key.startswith("F-R7-")

    def test_auto_mint_avoids_existing_slots(self):
        parsed = parse_peas_markdown(NO_SLOT_PEAS)
        existing = {"F-R7-001", "F-R7-002", "F-R7-003"}
        stubs = emit_stub_features(parsed, existing_slots=existing)
        assert stubs[0]["key"] not in existing

    def test_stub_has_required_keys(self):
        parsed = parse_peas_markdown(SIMPLE_PEAS)
        stubs = emit_stub_features(parsed)
        required = {"key", "title", "tier", "priority", "description", "acceptance_criteria"}
        for stub in stubs:
            assert required <= set(stub.keys())

    def test_title_preserved(self):
        parsed = parse_peas_markdown(SIMPLE_PEAS)
        stubs = emit_stub_features(parsed)
        assert stubs[0]["title"] == "My Feature"

    def test_description_preserved(self):
        parsed = parse_peas_markdown(SIMPLE_PEAS)
        stubs = emit_stub_features(parsed)
        assert "useful" in stubs[0]["description"]

    def test_empty_parsed_returns_empty(self):
        stubs = emit_stub_features([])
        assert stubs == []

    def test_multiple_auto_minted_slots_unique(self):
        text = "## A\nTier: Core  |  Priority: high\nDesc A.\n\n## B\nTier: Core  |  Priority: high\nDesc B.\n"
        parsed = parse_peas_markdown(text)
        stubs = emit_stub_features(parsed)
        keys = [s["key"] for s in stubs]
        assert len(keys) == len(set(keys))

    def test_yaml_roundtrip(self):
        parsed = parse_peas_markdown(SIMPLE_PEAS)
        stubs = emit_stub_features(parsed)
        output = {"features": stubs}
        dumped = yaml.safe_dump(output, sort_keys=False)
        reloaded = yaml.safe_load(dumped)
        assert len(reloaded["features"]) == 2


# ---------------------------------------------------------------------------
# _next_slot helper
# ---------------------------------------------------------------------------


class TestNextSlot:
    def test_first_slot_from_empty(self):
        result = _next_slot(set())
        assert result == "F-R7-001"

    def test_skips_occupied_slots(self):
        occupied = {"F-R7-001", "F-R7-002"}
        result = _next_slot(occupied)
        assert result == "F-R7-003"

    def test_handles_gaps(self):
        occupied = {"F-R7-001", "F-R7-003"}
        result = _next_slot(occupied)
        assert result == "F-R7-002"

    def test_ignores_non_r7_slots(self):
        occupied = {"F-R1-001"}
        result = _next_slot(occupied)
        assert result == "F-R7-001"


# ---------------------------------------------------------------------------
# Integration: parse → emit round-trip produces valid YAML
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_output_is_valid_yaml(self):
        peas = textwrap.dedent(
            """\
            ## Feature Alpha
            Tier: Core  |  Priority: high  |  Slot: F-R7-100
            Alpha does something.

            ## Feature Beta
            Tier: Infra  |  Priority: low  |  Slot: F-R7-101
            Beta does something else.
            """
        )
        parsed = parse_peas_markdown(peas)
        stubs = emit_stub_features(parsed)
        output = {"features": stubs}
        yaml_text = yaml.safe_dump(output, sort_keys=False)
        reloaded = yaml.safe_load(yaml_text)
        assert "features" in reloaded
        assert len(reloaded["features"]) == 2

    def test_stub_features_have_tbd_placeholder(self):
        peas = "## Solo Feature\nTier: Core  |  Priority: medium  |  Slot: F-R7-200\nDesc.\n"
        parsed = parse_peas_markdown(peas)
        stubs = emit_stub_features(parsed)
        assert stubs[0]["acceptance_criteria"] == [TBD_PLACEHOLDER]

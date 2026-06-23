"""Tests: SKIP sections are not penalized by extractor or critic."""

from __future__ import annotations

import pytest

from bob3.spec_quality.section_selector import (
    SectionSchemaError,
    critic_ignores_skip_slots,
    extractor_skips_marked_sections,
    module_set,
)


def _all_skip_map() -> dict[str, str]:
    """A section_map with all non-functional sections set to SKIP."""
    m = {s: "SKIP" for s in module_set()}
    m["functional"] = "REQUIRED"
    return m


def _all_required_map() -> dict[str, str]:
    return {s: "REQUIRED" for s in module_set()}


class TestExtractorSkipsMarkedSections:
    def test_null_skip_slot_is_ok(self):
        section_map = _all_skip_map()
        extraction = {s: None for s in module_set()}
        extraction["functional"] = {"acs": ["do something"]}
        assert extractor_skips_marked_sections(extraction, section_map) is True

    def test_rationale_dict_skip_slot_is_ok(self):
        section_map = _all_skip_map()
        extraction = {s: {"rationale": "not applicable"} for s in module_set() if s != "functional"}
        extraction["functional"] = {"acs": ["do something"]}
        assert extractor_skips_marked_sections(extraction, section_map) is True

    def test_non_null_non_rationale_skip_slot_fails(self):
        section_map = _all_skip_map()
        extraction = {s: None for s in module_set()}
        extraction["functional"] = {"acs": ["do something"]}
        extraction["perf"] = {"latency_budget_ms": 200}  # not rationale-annotated
        assert extractor_skips_marked_sections(extraction, section_map) is False

    def test_required_slot_with_value_is_ignored_by_this_check(self):
        section_map = _all_required_map()
        extraction = {s: {"data": "present"} for s in module_set()}
        assert extractor_skips_marked_sections(extraction, section_map) is True

    def test_empty_extraction_with_no_skip_sections_is_ok(self):
        section_map = _all_required_map()
        extraction: dict = {}
        assert extractor_skips_marked_sections(extraction, section_map) is True

    def test_mixed_skip_and_required_partial_pass(self):
        section_map = {s: "REQUIRED" for s in module_set()}
        section_map["perf"] = "SKIP"
        section_map["ux"] = "SKIP"
        extraction = {s: {"content": "filled"} for s in module_set()}
        extraction["perf"] = None  # correctly nulled
        extraction["ux"] = "some string"  # incorrectly filled
        assert extractor_skips_marked_sections(extraction, section_map) is False


class TestCriticIgnoresSkipSlots:
    def test_returns_true_for_valid_map(self):
        section_map = _all_skip_map()
        assert critic_ignores_skip_slots(section_map) is True

    def test_returns_true_for_all_required(self):
        assert critic_ignores_skip_slots(_all_required_map()) is True

    def test_raises_schema_error_for_invalid_map(self):
        bad_map = {s: "REQUIRED" for s in module_set() if s != "perf"}
        with pytest.raises(SectionSchemaError):
            critic_ignores_skip_slots(bad_map)

    def test_returns_true_for_mixed_valid_map(self):
        m = {s: "OPTIONAL" for s in module_set()}
        m["functional"] = "REQUIRED"
        assert critic_ignores_skip_slots(m) is True

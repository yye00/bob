"""Tests: select_sections output matches the required schema."""

from __future__ import annotations

import pytest

from bob3.spec_quality.section_selector import (
    SectionSchemaError,
    module_set,
    select_sections,
    validate_output_schema,
)

_VALID_VALUES = {"REQUIRED", "OPTIONAL", "SKIP"}


def _make_feature(name: str = "My feature", description: str = "", acs: list[str] | None = None):
    return {
        "feature_id": "test-feature-001",
        "name": name,
        "description": description,
        "acceptance_criteria": acs or [],
    }


class TestSelectSectionsOutputSchema:
    def test_returns_dict(self):
        out = select_sections(**_make_feature())
        assert isinstance(out, dict)

    def test_has_all_eight_sections(self):
        out = select_sections(**_make_feature())
        assert set(out.keys()) == set(module_set())

    def test_values_are_valid_labels(self):
        out = select_sections(**_make_feature())
        for section, value in out.items():
            assert value in _VALID_VALUES, f"{section!r} has invalid value {value!r}"

    def test_functional_always_required(self):
        out = select_sections(**_make_feature())
        assert out["functional"] == "REQUIRED"

    def test_schema_validation_accepts_valid_output(self):
        out = select_sections(**_make_feature())
        validate_output_schema(out)  # Must not raise

    def test_schema_validation_rejects_missing_key(self):
        bad = {s: "REQUIRED" for s in module_set() if s != "perf"}
        with pytest.raises(SectionSchemaError, match="missing sections"):
            validate_output_schema(bad)

    def test_schema_validation_rejects_extra_key(self):
        bad = {s: "REQUIRED" for s in module_set()}
        bad["invented_section"] = "SKIP"
        with pytest.raises(SectionSchemaError, match="unexpected sections"):
            validate_output_schema(bad)

    def test_schema_validation_rejects_invalid_value(self):
        bad = {s: "REQUIRED" for s in module_set()}
        bad["perf"] = "MAYBE"
        with pytest.raises(SectionSchemaError, match="Invalid value"):
            validate_output_schema(bad)

    def test_schema_validation_rejects_non_dict(self):
        with pytest.raises(SectionSchemaError):
            validate_output_schema(["REQUIRED"] * 8)

    def test_schema_validation_rejects_none(self):
        with pytest.raises(SectionSchemaError):
            validate_output_schema(None)

    def test_feature_with_security_keywords_marks_security_required_or_optional(self):
        f = _make_feature(description="Handles auth token encryption and permission checks")
        out = select_sections(**f)
        assert out["security"] in {"REQUIRED", "OPTIONAL"}

    def test_feature_with_perf_keywords_marks_perf_required_or_optional(self):
        f = _make_feature(description="Reduces latency and improves throughput of the pipeline")
        out = select_sections(**f)
        assert out["perf"] in {"REQUIRED", "OPTIONAL"}

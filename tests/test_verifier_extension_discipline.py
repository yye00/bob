"""Tests for enforce_ac_discipline and validate_ac_form in bob3.verifier_extension."""

from __future__ import annotations

import pytest

from bob3.verifier_extension import (
    VERIFIER_EXTENSION_MODULES,
    ACFilterResult,
    DemotedAC,
    enforce_ac_discipline,
    validate_ac_form,
)

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_other_module.py"


class TestEnforceAcDiscipline:
    def test_behavior_ac_is_demoted_for_verifier_extension_target(self):
        acs = ["behavior: output MUST contain X when Y"]
        result = enforce_ac_discipline(acs, _VERIFIER_TARGET, feature_id="test-feature")
        assert isinstance(result, ACFilterResult)
        assert result.is_verifier_extension is True
        assert len(result.demoted) == 1
        assert isinstance(result.demoted[0], DemotedAC)
        assert result.demoted[0].original == acs[0]
        assert "[SKIP" in result.filtered_acs[0]

    def test_structural_ac_passes_through_for_verifier_extension_target(self):
        acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
        result = enforce_ac_discipline(acs, _VERIFIER_TARGET)
        assert result.is_verifier_extension is True
        assert result.demoted == []
        assert result.filtered_acs == acs

    def test_pytest_ac_passes_through_for_verifier_extension_target(self):
        acs = ["pytest: tests/test_foo.py::test_bar"]
        result = enforce_ac_discipline(acs, _VERIFIER_TARGET)
        assert result.is_verifier_extension is True
        assert result.demoted == []
        assert result.filtered_acs == acs

    def test_integration_ac_passes_through_for_verifier_extension_target(self):
        acs = ["integration: bob3.spec_extractor"]
        result = enforce_ac_discipline(acs, _VERIFIER_TARGET)
        assert result.is_verifier_extension is True
        assert result.demoted == []
        assert result.filtered_acs == acs

    def test_behavior_ac_passes_through_for_normal_target(self):
        acs = ["behavior: output MUST contain X when Y"]
        result = enforce_ac_discipline(acs, _NORMAL_TARGET)
        assert result.is_verifier_extension is False
        assert result.demoted == []
        assert result.filtered_acs == acs

    def test_multiple_behavior_acs_all_demoted(self):
        acs = [
            "behavior: first behavior",
            "structural: file X contains Y",
            "behavior: second behavior",
        ]
        result = enforce_ac_discipline(acs, _VERIFIER_TARGET)
        assert len(result.demoted) == 2
        assert len(result.filtered_acs) == 3
        assert result.filtered_acs[1] == "structural: file X contains Y"

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            enforce_ac_discipline("not a list", _VERIFIER_TARGET)

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_ac_discipline(None, _VERIFIER_TARGET)

    def test_verifier_extension_modules_matched(self):
        for module_path in VERIFIER_EXTENSION_MODULES:
            result = enforce_ac_discipline(["behavior: test"], module_path)
            assert result.is_verifier_extension is True, f"Expected match for {module_path}"

    def test_empty_acs_returns_empty_result(self):
        result = enforce_ac_discipline([], _VERIFIER_TARGET)
        assert result.filtered_acs == []
        assert result.demoted == []
        assert result.is_verifier_extension is True

    def test_case_insensitive_behavior_prefix_is_caught(self):
        for ac in ["BEHAVIOR: uppercase", "Behavior: mixed"]:
            result = enforce_ac_discipline([ac], _VERIFIER_TARGET)
            assert len(result.demoted) == 1, f"Expected demotion for {ac!r}"


class TestValidateAcForm:
    def test_behavior_ac_is_invalid(self):
        result = validate_ac_form("behavior: output MUST contain X")
        assert result["valid"] is False
        assert result["form"] == "behavior"
        assert result["allowed_for_verifier_extension"] is False

    def test_structural_ac_is_valid(self):
        result = validate_ac_form("structural: file X contains Y")
        assert result["valid"] is True
        assert result["form"] == "structural"
        assert result["allowed_for_verifier_extension"] is True

    def test_integration_ac_is_valid(self):
        result = validate_ac_form("integration: bob3.spec_extractor")
        assert result["valid"] is True
        assert result["form"] == "integration"
        assert result["allowed_for_verifier_extension"] is True

    def test_pytest_ac_is_valid(self):
        result = validate_ac_form("pytest: tests/test_foo.py")
        assert result["valid"] is True
        assert result["form"] == "pytest"
        assert result["allowed_for_verifier_extension"] is True

    def test_file_exists_ac_is_valid(self):
        result = validate_ac_form("File exists: src/bob3/foo.py")
        assert result["valid"] is True
        assert result["form"] == "file_exists"
        assert result["allowed_for_verifier_extension"] is True

    def test_function_defined_ac_is_valid(self):
        result = validate_ac_form("Function defined: bob3.foo.bar")
        assert result["valid"] is True
        assert result["form"] == "function_defined"
        assert result["allowed_for_verifier_extension"] is True

    def test_class_defined_ac_is_valid(self):
        result = validate_ac_form("Class defined: bob3.foo.Bar")
        assert result["valid"] is True
        assert result["form"] == "class_defined"
        assert result["allowed_for_verifier_extension"] is True

    def test_unknown_form_is_invalid(self):
        result = validate_ac_form("some random text without a known prefix")
        assert result["valid"] is False
        assert result["form"] == "unknown"
        assert result["allowed_for_verifier_extension"] is False

    def test_non_string_raises_value_error(self):
        with pytest.raises(ValueError, match="ac must be a str"):
            validate_ac_form(123)

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_ac_form(None)

    def test_case_insensitive_behavior_detected(self):
        for ac in ["BEHAVIOR: X", "Behavior: Y"]:
            result = validate_ac_form(ac)
            assert result["form"] == "behavior", f"Expected 'behavior' for {ac!r}"
            assert result["allowed_for_verifier_extension"] is False

    def test_returns_dict_with_required_keys(self):
        result = validate_ac_form("pytest: tests/test_foo.py")
        assert "valid" in result
        assert "form" in result
        assert "allowed_for_verifier_extension" in result

"""Tests for bob3.verifier_extension_enforcer.

Covers:
  - is_verifier_extension_module: detects known verifier-extension paths
  - reject_behavior_ac: demotes behavior ACs for verifier-extension features,
    passes through ACs for non-verifier-extension features, raises ValueError
    on invalid input.
"""

from __future__ import annotations

import logging

import pytest

from bob3.verifier_extension_enforcer import (
    VERIFIER_EXTENSION_MODULES,
    is_verifier_extension_module,
    reject_behavior_ac,
)

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_unrelated_module.py"


# ---------------------------------------------------------------------------
# is_verifier_extension_module
# ---------------------------------------------------------------------------

class TestIsVerifierExtensionModule:
    def test_known_verifier_path_returns_true(self):
        for mod in VERIFIER_EXTENSION_MODULES:
            assert is_verifier_extension_module(mod) is True, f"Expected True for {mod!r}"

    def test_unknown_path_returns_false(self):
        assert is_verifier_extension_module("src/bob3/some_module.py") is False

    def test_empty_string_returns_false(self):
        assert is_verifier_extension_module("") is False

    def test_partial_match_in_path_still_detects(self):
        assert is_verifier_extension_module("src/bob3/enhanced_verification.py") is True

    def test_unrelated_module_returns_false(self):
        assert is_verifier_extension_module("src/bob3/database.py") is False

    def test_verifier_extension_modules_is_non_empty_tuple(self):
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert len(VERIFIER_EXTENSION_MODULES) > 0


# ---------------------------------------------------------------------------
# reject_behavior_ac
# ---------------------------------------------------------------------------

class TestRejectBehaviorAc:
    def test_behavior_ac_demoted_for_verifier_extension(self):
        acs = ["behavior: output MUST contain X"]
        result = reject_behavior_ac(acs, _VERIFIER_TARGET)
        assert result["is_verifier_extension"] is True
        assert len(result["demoted"]) == 1
        assert result["demoted"][0]["original"] == acs[0]
        assert "[SKIP" in result["filtered_acs"][0]

    def test_structural_ac_passes_through_for_verifier_extension(self):
        acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
        result = reject_behavior_ac(acs, _VERIFIER_TARGET)
        assert result["filtered_acs"] == acs
        assert result["demoted"] == []
        assert result["is_verifier_extension"] is True

    def test_integration_ac_passes_through_for_verifier_extension(self):
        acs = ["integration: pytest tests/test_foo.py::test_bar passes"]
        result = reject_behavior_ac(acs, _VERIFIER_TARGET)
        assert result["filtered_acs"] == acs
        assert result["demoted"] == []

    def test_mixed_acs_only_behavior_demoted(self):
        acs = [
            "structural: file X contains Y",
            "behavior: when Z runs, W MUST happen",
            "integration: pytest tests/test_x.py passes",
        ]
        result = reject_behavior_ac(acs, _VERIFIER_TARGET)
        assert len(result["demoted"]) == 1
        assert result["demoted"][0]["original"] == acs[1]
        assert result["filtered_acs"][0] == acs[0]
        assert "[SKIP" in result["filtered_acs"][1]
        assert result["filtered_acs"][2] == acs[2]

    def test_normal_feature_all_acs_pass_through(self):
        acs = ["behavior: when X, Y MUST happen", "structural: file Z has func A"]
        result = reject_behavior_ac(acs, _NORMAL_TARGET)
        assert result["is_verifier_extension"] is False
        assert result["filtered_acs"] == acs
        assert result["demoted"] == []

    def test_empty_acs_verifier_extension_returns_empty(self):
        result = reject_behavior_ac([], _VERIFIER_TARGET)
        assert result["filtered_acs"] == []
        assert result["demoted"] == []
        assert result["is_verifier_extension"] is True

    def test_empty_acs_normal_feature_returns_empty(self):
        result = reject_behavior_ac([], _NORMAL_TARGET)
        assert result["filtered_acs"] == []
        assert result["is_verifier_extension"] is False

    def test_empty_primary_diff_target_treated_as_non_verifier(self):
        acs = ["behavior: some behavior"]
        result = reject_behavior_ac(acs, "")
        assert result["is_verifier_extension"] is False
        assert result["filtered_acs"] == acs

    def test_no_feature_id_does_not_raise(self):
        result = reject_behavior_ac(["behavior: test"], _VERIFIER_TARGET)
        assert result["is_verifier_extension"] is True

    def test_feature_id_accepted(self):
        result = reject_behavior_ac(["behavior: test"], _VERIFIER_TARGET, feature_id="feat-123")
        assert result["is_verifier_extension"] is True

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            reject_behavior_ac("not a list", _VERIFIER_TARGET)

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            reject_behavior_ac(None, _VERIFIER_TARGET)

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            reject_behavior_ac(("behavior: test",), _VERIFIER_TARGET)

    def test_behavior_ac_case_insensitive(self):
        for prefix in ("BEHAVIOR:", "Behavior:", "behavior:"):
            acs = [f"{prefix} some behavior"]
            result = reject_behavior_ac(acs, _VERIFIER_TARGET)
            assert len(result["demoted"]) == 1, f"Expected demotion for prefix {prefix!r}"

    def test_warning_logged_per_demoted_ac(self):
        acs = ["behavior: first", "behavior: second"]
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Capture()
        log = logging.getLogger("bob3.verifier_extension_enforcer")
        log.addHandler(handler)
        try:
            result = reject_behavior_ac(acs, _VERIFIER_TARGET, feature_id="warn-test")
        finally:
            log.removeHandler(handler)

        assert len(result["demoted"]) == 2
        warnings = [r for r in records if r.levelno == logging.WARNING]
        assert len(warnings) == 2
        for rec in warnings:
            msg = rec.getMessage()
            assert "AC discipline" in msg

    def test_multiple_behavior_acs_all_demoted(self):
        acs = ["behavior: first", "behavior: second", "behavior: third"]
        result = reject_behavior_ac(acs, _VERIFIER_TARGET)
        assert len(result["demoted"]) == 3
        assert all("[SKIP" in ac for ac in result["filtered_acs"])

    def test_demoted_record_has_original_and_skip_note(self):
        acs = ["behavior: something must happen"]
        result = reject_behavior_ac(acs, _VERIFIER_TARGET)
        assert "original" in result["demoted"][0]
        assert "skip_note" in result["demoted"][0]
        assert result["demoted"][0]["original"] == acs[0]

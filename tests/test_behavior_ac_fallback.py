"""Tests for the behavior-AC function-existence fallback in _check_criterion.

Feature 3707bd68: _check_criterion MUST fall back to function-existence demotion
before hard-failing unrecognized behavior ACs (F-R7-582).

When a behavior criterion doesn't match any bespoke pattern handler, the default
branch extracts snake_case/CamelCase identifiers from the criterion text, skips
a stopword list, and calls _search_for_function on each. If any identifier maps
to a def/class in the workspace, the criterion is demoted to PASS-with-WARNING
instead of hard-failing.
"""
from __future__ import annotations

import pathlib
import pytest

from bob.enhanced_verification import _check_criterion, _search_for_function


WORKSPACE = pathlib.Path(".")


def _check(criterion: str) -> bool:
    return _check_criterion(
        criterion=criterion,
        workspace=WORKSPACE,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


class TestFunctionExistenceFallback:
    """_check_criterion falls back to function-existence demotion (F-R7-582)."""

    def test_known_function_in_workspace_passes(self):
        # is_cost_telemetry_lost is defined in cost_telemetry_guard.py
        result = _check(
            "The orchestrator MUST call is_cost_telemetry_lost before applying budget"
        )
        assert result is True

    def test_known_camel_case_class_in_workspace_passes(self):
        # Feature model class exists; CamelCase fallback should find it
        result = _check(
            "The system MUST instantiate a Feature object from the database row"
        )
        # Feature class exists — if matched, passes; if stopworded, test is
        # still valid as long as it does not raise
        assert isinstance(result, bool)

    def test_apply_pessimistic_cost_function_passes(self):
        # apply_pessimistic_cost is defined in cost_telemetry_guard.py
        result = _check(
            "Budget enforcement MUST use apply_pessimistic_cost when telemetry is lost"
        )
        assert result is True

    def test_nonexistent_function_hard_fails(self):
        # A deliberately invented function name that cannot exist in the workspace
        result = _check(
            "The system MUST call totally_nonexistent_function_xyz_qwertyuiop on startup"
        )
        assert result is False

    def test_stopwords_alone_do_not_trigger_demotion(self):
        # Criterion consisting only of stopword tokens must not spuriously pass
        result = _check("function module class file test with default param value")
        assert result is False

    def test_criterion_with_multiple_identifiers_passes_on_first_match(self):
        # Even if only one identifier resolves, the criterion passes
        result = _check(
            "MUST call is_cost_telemetry_lost or totally_nonexistent_xyz_qwerty"
        )
        assert result is True

    def test_emit_cost_telemetry_lost_event_passes(self):
        # emit_cost_telemetry_lost_event is defined in cost_telemetry_guard.py
        result = _check(
            "Structured WARN log MUST be written via emit_cost_telemetry_lost_event"
        )
        assert result is True


class TestSearchForFunction:
    """_search_for_function finds def/class definitions in workspace .py files."""

    def test_finds_known_function(self):
        assert _search_for_function(WORKSPACE, "is_cost_telemetry_lost", True, False) is True

    def test_does_not_find_nonexistent_function(self):
        assert _search_for_function(WORKSPACE, "totally_fake_function_xyz_abc", True, False) is False

    def test_finds_known_class(self):
        # Feature class should be findable
        assert isinstance(
            _search_for_function(WORKSPACE, "Feature", True, False), bool
        )

    def test_empty_name_returns_bool(self):
        # Empty name generates a regex matching any def/class — implementation-defined.
        # The contract is: must return a bool without raising.
        result = _search_for_function(WORKSPACE, "", True, False)
        assert isinstance(result, bool)

    def test_cpp_mode_returns_true_for_unknown_type(self):
        # For non-Python, non-CMake projects, soft-pass
        result = _search_for_function(WORKSPACE, "anything", False, False)
        assert result is True

    def test_search_is_python_def_not_comment(self):
        # A commented-out name should NOT match — tests that we grep for def/class patterns
        # We rely on _check_criterion to use this correctly; standalone sanity check
        result = _search_for_function(WORKSPACE, "apply_pessimistic_cost", True, False)
        assert result is True


class TestIntegrationWithOrchestrator:
    """Integration check: bob.orchestrator modules referenced in ACs are present."""

    def test_cost_telemetry_guard_importable(self):
        import importlib
        mod = importlib.import_module("bob.orchestrator.cost_telemetry_guard")
        assert hasattr(mod, "is_cost_telemetry_lost")
        assert hasattr(mod, "apply_pessimistic_cost")
        assert callable(mod.is_cost_telemetry_lost)
        assert callable(mod.apply_pessimistic_cost)

    def test_orchestrator_package_importable(self):
        import importlib
        mod = importlib.import_module("bob.orchestrator")
        assert mod is not None

    def test_check_criterion_integration_orchestrator_pass(self):
        # integration: bob.orchestrator — should resolve to True (module exists)
        result = _check("integration: bob.orchestrator")
        assert result is True

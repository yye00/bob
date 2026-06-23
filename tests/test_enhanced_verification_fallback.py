"""Tests for the F-R7-582 function-existence fallback in _check_criterion.

Verifies that _check_criterion falls back to function-existence demotion
(rather than hard-failing) when criterion text mentions a snake_case or
CamelCase identifier that resolves to `def NAME` / `class NAME` in the
workspace src tree.  Stopwords and bare single-lowercase-word tokens must
not trigger the fallback.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from bob3.enhanced_verification import _check_criterion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workspace(tmp_path: pathlib.Path, src_content: str, filename: str = "foo.py") -> pathlib.Path:
    """Create a minimal workspace with a src/bob3/<filename> containing src_content."""
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / filename).write_text(src_content)
    return tmp_path


def _check(criterion: str, workspace: pathlib.Path) -> bool:
    return _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


# ---------------------------------------------------------------------------
# Core integration tests required by ACs
# ---------------------------------------------------------------------------


class TestFunctionExistsDemotes:
    """AC: 'behavior: is_cost_telemetry_lost returns True when X' with a workspace
    containing `def is_cost_telemetry_lost` must return True (F-R7-582 demotion).
    """

    def test_function_exists_demotes(self, tmp_path):
        workspace = _make_workspace(
            tmp_path,
            "def is_cost_telemetry_lost(feature_id):\n    return False\n",
        )
        result = _check(
            "behavior: is_cost_telemetry_lost returns True when telemetry is unavailable",
            workspace,
        )
        assert result is True

    def test_snake_case_identifier_triggers_demotion(self, tmp_path):
        workspace = _make_workspace(
            tmp_path,
            "def apply_pessimistic_cost(feature_id, amount):\n    pass\n",
        )
        result = _check(
            "behavior: apply_pessimistic_cost MUST be invoked when budget is missing",
            workspace,
        )
        assert result is True

    def test_second_snake_case_identifier_in_criterion(self, tmp_path):
        workspace = _make_workspace(
            tmp_path,
            "def compute_budget_floor(x):\n    return x\n",
        )
        result = _check(
            "behavior: compute_budget_floor is invoked with a positive value",
            workspace,
        )
        assert result is True


class TestNoMatchStillFails:
    """AC: AC referencing only nonexistent identifiers must return False."""

    def test_no_match_still_fails(self, tmp_path):
        workspace = _make_workspace(tmp_path, "# empty module\n")
        result = _check(
            "behavior: nonexistent_function_xyz returns True when X",
            workspace,
        )
        assert result is False

    def test_multiple_nonexistent_identifiers_still_fails(self, tmp_path):
        workspace = _make_workspace(tmp_path, "# empty module\n")
        result = _check(
            "behavior: ghost_func_abc and phantom_helper_def must both be present",
            workspace,
        )
        assert result is False


class TestStopwordOnlyNoDemote:
    """AC: AC composed only of stopwords + literals must not trigger demotion."""

    def test_stopword_only_no_demote(self, tmp_path):
        # workspace has a function named "returns" — but "returns" is a stopword
        workspace = _make_workspace(
            tmp_path,
            "def returns(x):\n    return x\n",
        )
        result = _check(
            "behavior: function must returns true or false when value is null",
            workspace,
        )
        # All snake_case identifiers in this criterion are stopwords
        assert result is False

    def test_stopword_behavior_no_demote(self, tmp_path):
        workspace = _make_workspace(tmp_path, "def behavior():\n    pass\n")
        result = _check("behavior: structural integration must shall returns true", workspace)
        assert result is False


# ---------------------------------------------------------------------------
# CamelCase fallback
# ---------------------------------------------------------------------------


class TestCamelCaseFallback:
    """AC: _check_criterion returns True when criterion mentions a CamelCase
    identifier (≥2 uppercase letters) that resolves to `class NAME` in workspace.
    """

    def test_camel_case_class_demotes(self, tmp_path):
        workspace = _make_workspace(
            tmp_path,
            "class CostTelemetryGuard:\n    pass\n",
        )
        result = _check(
            "behavior: CostTelemetryGuard is instantiated on startup",
            workspace,
        )
        assert result is True

    def test_camel_case_with_many_uppers_demotes(self, tmp_path):
        workspace = _make_workspace(
            tmp_path,
            "class BudgetEnforcementPolicy:\n    pass\n",
        )
        result = _check(
            "behavior: BudgetEnforcementPolicy.apply must be called",
            workspace,
        )
        assert result is True


class TestCamelCaseNotTriggedByOneUppercase:
    """Single-capital words like 'True', 'False', 'None' must not qualify."""

    def test_single_uppercase_word_not_demoted(self, tmp_path):
        workspace = _make_workspace(tmp_path, "def Config():\n    pass\n")
        # 'Config' has only one uppercase letter — should NOT trigger CamelCase fallback
        result = _check(
            "behavior: Config must be loaded on startup returns False",
            workspace,
        )
        # 'Config' won't match r"\b([A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*)\b"
        assert result is False


# ---------------------------------------------------------------------------
# Bare single-word lowercase tokens must not trigger fallback
# ---------------------------------------------------------------------------


class TestBareWordTokensNotTriggered:
    """AC: bare single-word lowercase tokens must NOT trigger the fallback even
    if a same-named function exists; only snake_case (≥1 underscore) or CamelCase
    (≥2 uppercase) identifiers qualify.
    """

    def test_bare_lowercase_spec_no_demote(self, tmp_path):
        workspace = _make_workspace(tmp_path, "def spec():\n    pass\n")
        result = _check("behavior: spec must return value", workspace)
        assert result is False

    def test_bare_lowercase_process_no_demote(self, tmp_path):
        workspace = _make_workspace(tmp_path, "def process():\n    pass\n")
        result = _check("behavior: process must run correctly", workspace)
        assert result is False

    def test_bare_lowercase_config_no_demote(self, tmp_path):
        workspace = _make_workspace(tmp_path, "def config():\n    pass\n")
        result = _check("behavior: config must be loaded on startup", workspace)
        assert result is False


# ---------------------------------------------------------------------------
# Warning log contains F-R7-582
# ---------------------------------------------------------------------------


class TestFallbackEmitsF_R7_582Warning:
    """AC: when the fallback demotes a criterion to PASS it MUST emit a warning
    log line containing 'F-R7-582'.
    """

    def test_warning_contains_f_r7_582(self, tmp_path, caplog):
        workspace = _make_workspace(
            tmp_path,
            "def is_cost_telemetry_lost(feature_id):\n    return False\n",
        )
        with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
            result = _check(
                "behavior: is_cost_telemetry_lost returns True when telemetry is unavailable",
                workspace,
            )
        assert result is True
        assert any("F-R7-582" in record.message for record in caplog.records), (
            "Expected a warning log containing 'F-R7-582' but none was emitted. "
            f"Log records: {[r.message for r in caplog.records]}"
        )

    def test_warning_not_emitted_on_false(self, tmp_path, caplog):
        workspace = _make_workspace(tmp_path, "# empty\n")
        with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
            result = _check(
                "behavior: nonexistent_function_xyz must return true",
                workspace,
            )
        assert result is False
        assert not any("F-R7-582" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Structural AC: _check_criterion calls _search_for_function in default branch
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Top-level integration tests with exact names required by ACs
# ---------------------------------------------------------------------------


def test_function_exists_demotes(tmp_path):
    """AC: 'behavior: is_cost_telemetry_lost returns True when X' with a workspace
    containing `def is_cost_telemetry_lost` returns True (F-R7-582 demotion).
    """
    workspace = _make_workspace(
        tmp_path,
        "def is_cost_telemetry_lost(feature_id):\n    return False\n",
    )
    result = _check(
        "behavior: is_cost_telemetry_lost returns True when telemetry is unavailable",
        workspace,
    )
    assert result is True


def test_no_match_still_fails(tmp_path):
    """AC: AC referencing only nonexistent identifiers returns False."""
    workspace = _make_workspace(tmp_path, "# empty module\n")
    result = _check(
        "behavior: nonexistent_function_xyz returns True when X",
        workspace,
    )
    assert result is False


def test_stopword_only_no_demote(tmp_path):
    """AC: AC composed only of stopwords + literals does not trigger demotion."""
    workspace = _make_workspace(
        tmp_path,
        "def returns(x):\n    return x\n",
    )
    result = _check(
        "behavior: function must returns true or false when value is null",
        workspace,
    )
    assert result is False


class TestCheckCriterionStructural:
    """Structural checks: _check_criterion is defined and the module exists."""

    def test_module_defines_check_criterion(self):
        import bob3.enhanced_verification as ev
        assert callable(ev._check_criterion)

    def test_module_defines_search_for_function(self):
        import bob3.enhanced_verification as ev
        assert callable(ev._search_for_function)

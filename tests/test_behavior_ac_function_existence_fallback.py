"""Behavior-AC function-existence fallback (feature 96a75ec3).

When a behavior AC does not match any bespoke pattern handler, the verifier's
default branch MUST extract snake_case / CamelCase identifiers, skip a stopword
list, and demote to PASS-with-warning if any identifier resolves to a
``def NAME`` / ``class NAME`` in the workspace src tree — rather than
hard-failing. This mirrors the prose-AC / integration-AC demotion philosophy
(F-R7-576 / F-R7-577 / F-R7-582): if the spec's claim is structurally
observable, accept it.
"""
import pathlib

import pytest

from bob import enhanced_verification as ev


def _check(criterion: str, workspace: pathlib.Path) -> bool:
    return ev._check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


@pytest.fixture
def py_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    src = tmp_path / "src" / "bob" / "orchestrator"
    src.mkdir(parents=True)
    (src / "cost_telemetry_guard.py").write_text(
        "def is_cost_telemetry_lost(reported_cost, work_events):\n"
        "    return False\n\n\n"
        "def apply_pessimistic_cost(reported_cost, is_lost, ceiling):\n"
        "    return 0.0\n\n\n"
        "class TelemetryVerdict:\n"
        "    pass\n"
    )
    return tmp_path


def test_snake_case_identifier_demotes_to_pass(py_workspace):
    # The exact regression from the feature: a behavior AC naming a snake_case
    # function that DOES exist must PASS via the fallback, not hard-fail.
    criterion = (
        "behavior: when telemetry is lost the guard MUST call "
        "is_cost_telemetry_lost before charging the feature"
    )
    assert _check(criterion, py_workspace) is True


def test_second_referenced_function_demotes_to_pass(py_workspace):
    criterion = (
        "behavior: apply_pessimistic_cost MUST charge the per-feature ceiling "
        "when telemetry is missing"
    )
    assert _check(criterion, py_workspace) is True


def test_camelcase_identifier_demotes_to_pass(py_workspace):
    criterion = "behavior: verifier constructs a TelemetryVerdict for the caller"
    assert _check(criterion, py_workspace) is True


def test_unresolvable_identifier_hard_fails(py_workspace):
    # An identifier that does NOT exist anywhere must still hard-fail — the
    # fallback is not a blanket pass-everything.
    criterion = (
        "behavior: the guard MUST invoke reconcile_nonexistent_symbol_xyz "
        "before proceeding"
    )
    assert _check(criterion, py_workspace) is False


def test_stopword_only_criterion_hard_fails(py_workspace):
    # A criterion whose only extractable tokens are stopwords must not spuriously
    # pass just because some function happens to exist.
    criterion = "behavior: the function must return the value when this file tests pass"
    assert _check(criterion, py_workspace) is False


def test_search_for_function_finds_existing_def(py_workspace):
    assert ev._search_for_function(
        py_workspace, "is_cost_telemetry_lost", True, False
    ) is True


def test_search_for_function_missing_returns_false(py_workspace):
    assert ev._search_for_function(
        py_workspace, "definitely_not_here_xyz", True, False
    ) is False


def test_check_criterion_and_search_are_defined():
    assert callable(ev._check_criterion)
    assert callable(ev._search_for_function)

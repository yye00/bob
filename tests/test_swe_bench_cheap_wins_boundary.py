"""Boundary case tests for SWE-Bench cheap wins in bob3.dispatch (F-R7-609).

AC: empty, zero, or minimum input returns a well-defined result rather than raising.

Covers boundary inputs for all four cheap-win directives:
  (A) repo_tree — empty workspace, zero files
  (B) failing_repro_test — empty/None ACs
  (C) adaptive EDIT_MODE — zero sites, zero span, at-threshold values
  (D) mutation-pass check — minimal command, empty feature_id
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob3.dispatch import (
    EditModeDecision,
    apply_cheap_wins,
    build_repo_tree,
    build_worker_system_prompt,
    check_mutation_pass,
    compute_edit_mode,
    emit_edit_mode_event,
    emit_weak_test_event,
    inject_failing_repro_test_directive,
    inject_repo_tree_into_prompt,
    run_mutation_pass_check,
    select_edit_mode,
    should_inject_repro_test_directive,
)


def make_feature(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": "feat-boundary-001",
        "name": "Boundary Test Feature",
        "acceptance_criteria": '["pytest: tests/test_foo.py"]',
        "skip_repro_test": False,
        "skip_repo_tree": False,
        "localization_shortlist": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── (A) repo_tree boundary cases ──────────────────────────────────────────────


class TestRepoTreeBoundary:
    def test_empty_workspace_returns_string(self, tmp_path):
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_empty_workspace_does_not_raise(self, tmp_path):
        # No files in directory — should not raise
        result = build_repo_tree(tmp_path)
        assert result is not None

    def test_max_lines_of_one_returns_string(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=1)
        assert isinstance(result, str)

    def test_max_lines_of_one_with_many_files_truncates(self, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=1)
        assert isinstance(result, str)
        assert "more" in result

    def test_inject_with_empty_prompt_returns_string(self, tmp_path):
        result = inject_repo_tree_into_prompt("", tmp_path)
        assert isinstance(result, str)

    def test_inject_with_single_char_prompt(self, tmp_path):
        result = inject_repo_tree_into_prompt("x", tmp_path)
        assert "x" in result

    def test_string_workspace_path_accepted(self, tmp_path):
        result = build_repo_tree(str(tmp_path))
        assert isinstance(result, str)


# ── (B) failing_repro_test boundary cases ────────────────────────────────────


class TestFailingReproTestBoundary:
    def test_none_acceptance_criteria_does_not_raise(self):
        feature = make_feature(acceptance_criteria=None)
        result = should_inject_repro_test_directive(feature)
        assert isinstance(result, bool)

    def test_empty_string_acceptance_criteria_does_not_raise(self):
        feature = make_feature(acceptance_criteria="")
        result = should_inject_repro_test_directive(feature)
        assert isinstance(result, bool)

    def test_empty_list_acceptance_criteria_does_not_raise(self):
        feature = make_feature(acceptance_criteria="[]")
        result = should_inject_repro_test_directive(feature)
        assert isinstance(result, bool)

    def test_inject_with_empty_base_prompt(self):
        result = inject_failing_repro_test_directive("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_inject_with_single_char_prompt(self):
        result = inject_failing_repro_test_directive("x")
        assert "x" in result

    def test_feature_without_id_attribute_does_not_raise(self, tmp_path):
        feature = SimpleNamespace(
            name="No-ID Feature",
            acceptance_criteria=None,
            skip_repro_test=False,
            skip_repo_tree=False,
            localization_shortlist=[],
        )
        result, meta = apply_cheap_wins("prompt", tmp_path, feature)
        assert isinstance(result, str)

    def test_build_worker_system_prompt_with_empty_prompt(self, tmp_path):
        feature = make_feature()
        result = build_worker_system_prompt("", tmp_path, feature)
        assert isinstance(result, str)


# ── (C) EDIT_MODE boundary cases ──────────────────────────────────────────────


class TestEditModeBoundary:
    def test_zero_sites_zero_span_is_replace(self):
        d = select_edit_mode(0, 0)
        assert d.mode == "replace"

    def test_zero_sites_zero_span_returns_decision(self):
        d = select_edit_mode(0, 0)
        assert isinstance(d, EditModeDecision)
        assert d.sites == 0
        assert d.span == 0

    def test_exactly_at_site_threshold_is_replace(self):
        # > 3 triggers rewrite; == 3 is still replace
        d = select_edit_mode(3, 0)
        assert d.mode == "replace"

    def test_exactly_at_span_threshold_is_replace(self):
        # > 40 triggers rewrite; == 40 is still replace
        d = select_edit_mode(0, 40)
        assert d.mode == "replace"

    def test_one_site_one_span_is_replace(self):
        d = select_edit_mode(1, 1)
        assert d.mode == "replace"

    def test_compute_edit_mode_zero_inputs(self):
        d = compute_edit_mode(0, 0)
        assert d.mode == "replace"
        assert d.sites == 0
        assert d.span == 0

    def test_emit_edit_mode_event_with_zero_values(self):
        d = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(d)
        assert event["sites"] == 0
        assert event["span"] == 0

    def test_emit_edit_mode_event_without_feature_id(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert "feature_id" not in event

    def test_apply_cheap_wins_zero_edit_counts(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature)
        assert meta["edit_mode"]["sites"] == 0
        assert meta["edit_mode"]["span"] == 0
        assert meta["edit_mode"]["mode"] == "replace"


# ── (D) mutation-pass check boundary cases ────────────────────────────────────


class TestMutationPassCheckBoundary:
    def test_empty_feature_id_does_not_raise(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "")
        assert isinstance(result, bool)

    def test_single_command_element_does_not_raise(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["echo"], tmp_path, "feat-001")
        assert isinstance(result, bool)

    def test_emit_weak_test_event_empty_feature_id(self):
        event = emit_weak_test_event("")
        assert isinstance(event, dict)
        assert event["feature_id"] == ""

    def test_emit_weak_test_event_no_detail_key_when_none(self):
        event = emit_weak_test_event("feat-001", detail=None)
        assert "detail" not in event

    def test_check_mutation_pass_returns_bool(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = check_mutation_pass(["echo"], tmp_path, "feat-001")
        assert isinstance(result, bool)

    def test_run_mutation_pass_check_string_workspace(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["echo"], str(tmp_path), "feat-001")
        assert isinstance(result, bool)

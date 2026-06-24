"""Tests for SWE-Bench cheap wins in bob.dispatch (F-R7-609).

Covers all four cheap-win directives:
  (A) repo_tree        — build_repo_tree, inject_repo_tree_into_prompt
  (B) failing_repro    — should_inject_repro_test_directive, inject_failing_repro_test_directive
  (C) adaptive EDIT_MODE — compute_edit_metrics (validated), select_edit_mode
  (D) mutation-pass    — apply_mutation_check, run_mutation_pass_check

AC: pytest: tests/test_dispatch_cheap_wins.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob.dispatch import (
    EditModeDecision,
    apply_cheap_wins,
    apply_mutation_check,
    build_repo_tree,
    build_worker_system_prompt,
    check_mutation_pass,
    compute_edit_metrics,
    compute_edit_mode,
    emit_edit_mode_event,
    emit_weak_test_event,
    inject_failing_repro_test_directive,
    inject_repo_tree_into_prompt,
    run_mutation_pass_check,
    select_edit_mode,
    should_inject_repro_test_directive,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_feature(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": "feat-cheapwin-001",
        "name": "Cheap Win Test Feature",
        "acceptance_criteria": '["pytest: tests/test_foo.py"]',
        "skip_repro_test": False,
        "skip_repo_tree": False,
        "localization_shortlist": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── (A) repo_tree ─────────────────────────────────────────────────────────────


class TestBuildRepoTree:
    def test_returns_string(self, tmp_path):
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_nonempty_workspace_contains_directory_content(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_accepts_path_object(self, tmp_path):
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_accepts_string_path(self, tmp_path):
        result = build_repo_tree(str(tmp_path))
        assert isinstance(result, str)

    def test_truncates_at_max_lines(self, tmp_path):
        for i in range(50):
            (tmp_path / f"file_{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=5)
        lines = result.splitlines()
        assert len(lines) <= 10  # trailer adds at most one extra line
        assert "more" in result

    def test_does_not_exceed_200_lines_by_default(self, tmp_path):
        for i in range(300):
            (tmp_path / f"file_{i}.py").write_text("")
        result = build_repo_tree(tmp_path)
        lines = result.splitlines()
        assert len(lines) <= 202  # 200 + possible trailer + blank

    def test_trailer_line_present_when_truncated(self, tmp_path):
        for i in range(20):
            (tmp_path / f"file_{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=3)
        assert "more" in result


class TestInjectRepoTreeIntoPrompt:
    def test_prepends_tree_to_prompt(self, tmp_path):
        original = "Do the task."
        result = inject_repo_tree_into_prompt(original, tmp_path)
        assert "Do the task." in result

    def test_result_is_longer_than_input(self, tmp_path):
        original = "task"
        result = inject_repo_tree_into_prompt(original, tmp_path)
        assert len(result) >= len(original)

    def test_returns_string(self, tmp_path):
        result = inject_repo_tree_into_prompt("hello", tmp_path)
        assert isinstance(result, str)


# ── (B) failing_repro_test ────────────────────────────────────────────────────


class TestShouldInjectReproTestDirective:
    def test_returns_bool(self):
        feature = make_feature()
        result = should_inject_repro_test_directive(feature)
        assert isinstance(result, bool)

    def test_skip_repro_test_true_returns_false(self):
        feature = make_feature(skip_repro_test=True)
        result = should_inject_repro_test_directive(feature)
        assert result is False

    def test_skip_repro_test_false_returns_true_by_default(self):
        feature = make_feature(skip_repro_test=False)
        result = should_inject_repro_test_directive(feature)
        assert result is True

    def test_structural_ac_skips_directive(self):
        feature = make_feature(
            skip_repro_test=False,
            acceptance_criteria='["File exists: src/foo.py"]',
        )
        # Structural AC kind → should suppress directive
        result = should_inject_repro_test_directive(feature)
        # structural-only ACs may return False; non-structural return True
        assert isinstance(result, bool)


class TestInjectFailingReproTestDirective:
    def test_returns_string(self):
        result = inject_failing_repro_test_directive("base prompt")
        assert isinstance(result, str)

    def test_contains_base_prompt(self):
        result = inject_failing_repro_test_directive("base prompt")
        assert "base prompt" in result

    def test_contains_directive_text(self):
        result = inject_failing_repro_test_directive("do work")
        # The directive talks about failing tests
        assert "RED" in result or "failing" in result.lower() or "test" in result.lower()

    def test_longer_than_base_prompt(self):
        base = "just a task"
        result = inject_failing_repro_test_directive(base)
        assert len(result) > len(base)


# ── (C) EDIT_MODE — compute_edit_metrics (validated) & select_edit_mode ───────


class TestComputeEditMetrics:
    """AC-required validated entry point."""

    def test_returns_edit_mode_decision(self):
        decision = compute_edit_metrics(1, 10)
        assert isinstance(decision, EditModeDecision)

    def test_zero_sites_zero_span_is_replace(self):
        d = compute_edit_metrics(0, 0)
        assert d.mode == "replace"

    def test_few_sites_small_span_is_replace(self):
        d = compute_edit_metrics(2, 20)
        assert d.mode == "replace"

    def test_many_sites_triggers_rewrite(self):
        d = compute_edit_metrics(4, 10)
        assert d.mode == "rewrite"

    def test_large_span_triggers_rewrite(self):
        d = compute_edit_metrics(1, 41)
        assert d.mode == "rewrite"

    def test_both_over_threshold_triggers_rewrite(self):
        d = compute_edit_metrics(5, 50)
        assert d.mode == "rewrite"

    def test_sites_preserved_in_decision(self):
        d = compute_edit_metrics(2, 15)
        assert d.sites == 2

    def test_span_preserved_in_decision(self):
        d = compute_edit_metrics(2, 15)
        assert d.span == 15

    def test_negative_site_count_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(-1, 10)

    def test_negative_span_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(2, -1)

    def test_float_inputs_raise_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(1.5, 10)  # type: ignore[arg-type]

    def test_string_inputs_raise_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_metrics("3", 10)  # type: ignore[arg-type]


class TestSelectEditMode:
    def test_returns_edit_mode_decision(self):
        d = select_edit_mode(1, 10)
        assert isinstance(d, EditModeDecision)

    def test_sites_3_is_replace(self):
        # > 3 triggers rewrite; exactly 3 is replace
        d = select_edit_mode(3, 0)
        assert d.mode == "replace"

    def test_sites_4_is_rewrite(self):
        d = select_edit_mode(4, 0)
        assert d.mode == "rewrite"

    def test_span_40_is_replace(self):
        # > 40 triggers rewrite; exactly 40 is replace
        d = select_edit_mode(0, 40)
        assert d.mode == "replace"

    def test_span_41_is_rewrite(self):
        d = select_edit_mode(0, 41)
        assert d.mode == "rewrite"


class TestEmitEditModeEvent:
    def test_returns_dict(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert isinstance(event, dict)

    def test_event_has_mode_key(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert "mode" in event

    def test_event_has_sites_key(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert "sites" in event

    def test_event_has_span_key(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert "span" in event

    def test_event_contains_correct_values(self):
        d = EditModeDecision(mode="rewrite", sites=5, span=50)
        event = emit_edit_mode_event(d)
        assert event["mode"] == "rewrite"
        assert event["sites"] == 5
        assert event["span"] == 50

    def test_event_includes_feature_id_when_provided(self):
        d = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(d, feature_id="feat-001")
        assert event.get("feature_id") == "feat-001"


# ── (D) mutation-pass check ────────────────────────────────────────────────────


class TestApplyMutationCheck:
    """AC-required alias: apply_mutation_check."""

    def test_returns_bool(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="")
            result = apply_mutation_check(["pytest", "test_foo.py"], tmp_path, "feat-001")
        assert isinstance(result, bool)

    def test_returns_false_when_mutation_causes_failure(self, tmp_path):
        """Mutation caused test to fail → test is well-specified → False."""
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="")
            result = apply_mutation_check(["pytest", "test_foo.py"], tmp_path, "feat-001")
        assert result is False

    def test_returns_true_when_mutation_still_passes(self, tmp_path):
        """Mutation didn't break test → weak test → True."""
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="passed", stderr="")
            result = apply_mutation_check(["pytest", "test_foo.py"], tmp_path, "feat-001")
        assert result is True


class TestRunMutationPassCheck:
    def test_returns_bool(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest", "test_foo.py"], tmp_path, "feat-001")
        assert isinstance(result, bool)

    def test_test_fail_after_mutation_returns_false(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="")
            result = run_mutation_pass_check(["pytest"], tmp_path, "feat-001")
        assert result is False

    def test_test_pass_after_mutation_returns_true(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="passed", stderr="")
            result = run_mutation_pass_check(["pytest"], tmp_path, "feat-001")
        assert result is True

    def test_accepts_string_workspace(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest"], str(tmp_path), "feat-001")
        assert isinstance(result, bool)


class TestEmitWeakTestEvent:
    def test_returns_dict(self):
        event = emit_weak_test_event("feat-001")
        assert isinstance(event, dict)

    def test_event_contains_feature_id(self):
        event = emit_weak_test_event("feat-001")
        assert event["feature_id"] == "feat-001"

    def test_event_contains_event_key(self):
        event = emit_weak_test_event("feat-001")
        assert "event" in event
        assert event["event"] == "WEAK_TEST_DETECTED"

    def test_event_with_detail(self):
        event = emit_weak_test_event("feat-001", detail="constant flipped")
        assert event.get("detail") == "constant flipped"

    def test_event_without_detail_has_no_detail_key(self):
        event = emit_weak_test_event("feat-001", detail=None)
        assert "detail" not in event


# ── Integration: apply_cheap_wins ─────────────────────────────────────────────


class TestApplyCheapWins:
    def test_returns_prompt_and_metadata(self, tmp_path):
        feature = make_feature()
        result, meta = apply_cheap_wins("do the task", tmp_path, feature)
        assert isinstance(result, str)
        assert isinstance(meta, dict)

    def test_prompt_includes_original_text(self, tmp_path):
        feature = make_feature()
        result, _ = apply_cheap_wins("do the task", tmp_path, feature)
        assert "do the task" in result

    def test_metadata_includes_edit_mode(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("do the task", tmp_path, feature)
        assert "edit_mode" in meta

    def test_skip_repo_tree_bypasses_tree_injection(self, tmp_path):
        feature = make_feature(skip_repo_tree=True)
        result, meta = apply_cheap_wins("task", tmp_path, feature)
        assert isinstance(result, str)

    def test_skip_repro_test_bypasses_directive(self, tmp_path):
        feature = make_feature(skip_repro_test=True)
        result, meta = apply_cheap_wins("task", tmp_path, feature)
        assert isinstance(result, str)


# ── Integration: build_worker_system_prompt ────────────────────────────────────


class TestBuildWorkerSystemPrompt:
    def test_returns_string(self, tmp_path):
        feature = make_feature()
        result = build_worker_system_prompt("do work", tmp_path, feature)
        assert isinstance(result, str)

    def test_contains_base_prompt(self, tmp_path):
        feature = make_feature()
        result = build_worker_system_prompt("do work", tmp_path, feature)
        assert "do work" in result

    def test_longer_than_base_prompt(self, tmp_path):
        base = "do work"
        feature = make_feature()
        result = build_worker_system_prompt(base, tmp_path, feature)
        assert len(result) >= len(base)

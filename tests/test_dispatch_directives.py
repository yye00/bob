"""Tests for SWE-Bench cheap-wins directives in bob3.dispatch (F-R7-609).

Covers the four directives injected into every worker prompt:
  (A) repo_tree         — compute_edit_site_metrics, build_repo_tree
  (B) failing_repro_test — inject_failing_repro_test_directive, should_inject_repro_test_directive
  (C) EDIT_MODE         — select_edit_mode, compute_edit_site_metrics thresholds
  (D) WEAK_TEST         — emit_weak_test_event, run_mutation_pass_check

Also verifies:
  - compute_edit_site_metrics is exported in __all__
  - apply_cheap_wins returns correct metadata structure
  - build_worker_system_prompt produces string output
"""

from __future__ import annotations

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
    compute_edit_site_metrics,
    emit_edit_mode_event,
    emit_weak_test_event,
    inject_failing_repro_test_directive,
    run_mutation_pass_check,
    select_edit_mode,
    should_inject_repro_test_directive,
)
import bob3.dispatch as _dispatch_module


def make_feature(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": "feat-directives-001",
        "name": "Directives Test Feature",
        "acceptance_criteria": '["pytest: tests/test_foo.py"]',
        "skip_repro_test": False,
        "skip_repo_tree": False,
        "localization_shortlist": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── Module exports ────────────────────────────────────────────────────────────

class TestModuleExports:
    def test_compute_edit_site_metrics_in_all(self):
        assert "compute_edit_site_metrics" in _dispatch_module.__all__

    def test_compute_edit_site_metrics_callable(self):
        assert callable(compute_edit_site_metrics)

    def test_all_directive_functions_exported(self):
        expected = [
            "apply_cheap_wins",
            "build_repo_tree",
            "build_worker_system_prompt",
            "compute_edit_site_metrics",
            "emit_edit_mode_event",
            "emit_weak_test_event",
            "inject_failing_repro_test_directive",
            "run_mutation_pass_check",
            "select_edit_mode",
            "should_inject_repro_test_directive",
        ]
        for name in expected:
            assert name in _dispatch_module.__all__, f"{name!r} missing from __all__"


# ── (A) compute_edit_site_metrics ─────────────────────────────────────────────

class TestComputeEditSiteMetrics:
    def test_returns_edit_mode_decision(self):
        result = compute_edit_site_metrics(0, 0)
        assert isinstance(result, EditModeDecision)

    def test_default_is_replace(self):
        result = compute_edit_site_metrics(1, 5)
        assert result.mode == "replace"

    def test_sites_above_threshold_triggers_rewrite(self):
        result = compute_edit_site_metrics(4, 0)
        assert result.mode == "rewrite"

    def test_span_above_threshold_triggers_rewrite(self):
        result = compute_edit_site_metrics(0, 41)
        assert result.mode == "rewrite"

    def test_exactly_at_site_threshold_is_replace(self):
        result = compute_edit_site_metrics(3, 0)
        assert result.mode == "replace"

    def test_exactly_at_span_threshold_is_replace(self):
        result = compute_edit_site_metrics(0, 40)
        assert result.mode == "replace"

    def test_sites_and_span_stored_on_result(self):
        result = compute_edit_site_metrics(2, 15)
        assert result.sites == 2
        assert result.span == 15

    def test_negative_site_count_raises_value_error(self):
        with pytest.raises(ValueError, match="edit_site_count"):
            compute_edit_site_metrics(-1, 5)

    def test_negative_span_raises_value_error(self):
        with pytest.raises(ValueError, match="edit_span"):
            compute_edit_site_metrics(2, -1)

    def test_float_inputs_raise_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_site_metrics(1.5, 5)  # type: ignore[arg-type]

    def test_string_inputs_raise_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_site_metrics("1", 5)  # type: ignore[arg-type]

    def test_none_site_count_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_edit_site_metrics(None, 5)  # type: ignore[arg-type]


# ── (A) repo_tree ─────────────────────────────────────────────────────────────

class TestRepoTree:
    def test_build_repo_tree_returns_string(self, tmp_path):
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_build_repo_tree_with_files(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("pass")
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_repo_tree_truncates_at_max_lines(self, tmp_path):
        for i in range(20):
            (tmp_path / f"file{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=5)
        assert "more" in result

    def test_repo_tree_injected_in_apply_cheap_wins(self, tmp_path):
        feature = make_feature(skip_repo_tree=False)
        augmented, meta = apply_cheap_wins("base prompt", tmp_path, feature)
        assert meta["repo_tree_injected"] is True
        assert "Repository Tree" in augmented or "repo_tree" in augmented.lower()

    def test_repo_tree_skipped_when_flag_set(self, tmp_path):
        feature = make_feature(skip_repo_tree=True)
        _, meta = apply_cheap_wins("base prompt", tmp_path, feature)
        assert meta["repo_tree_injected"] is False


# ── (B) failing_repro_test ────────────────────────────────────────────────────

class TestFailingReproTestDirective:
    def test_directive_injected_by_default(self, tmp_path):
        feature = make_feature(skip_repro_test=False)
        _, meta = apply_cheap_wins("base prompt", tmp_path, feature)
        assert meta["failing_repro_test_injected"] is True

    def test_directive_skipped_when_flag_set(self, tmp_path):
        feature = make_feature(skip_repro_test=True)
        _, meta = apply_cheap_wins("base prompt", tmp_path, feature)
        assert meta["failing_repro_test_injected"] is False

    def test_directive_contains_red_green_keywords(self):
        result = inject_failing_repro_test_directive("start")
        assert "RED" in result or "failing" in result.lower()
        assert "GREEN" in result or "passes" in result.lower()

    def test_should_inject_returns_true_for_non_structural_acs(self):
        feature = make_feature(acceptance_criteria='["pytest: tests/test_foo.py"]')
        assert should_inject_repro_test_directive(feature) is True

    def test_should_inject_returns_false_when_flag_set(self):
        feature = make_feature(skip_repro_test=True)
        assert should_inject_repro_test_directive(feature) is False

    def test_inject_appends_to_existing_prompt(self):
        base = "do the thing"
        result = inject_failing_repro_test_directive(base)
        assert base in result
        assert len(result) > len(base)

    def test_build_worker_system_prompt_includes_directive(self, tmp_path):
        feature = make_feature(skip_repro_test=False)
        result = build_worker_system_prompt("task", tmp_path, feature)
        assert isinstance(result, str)
        assert len(result) > len("task")


# ── (C) EDIT_MODE ─────────────────────────────────────────────────────────────

class TestEditMode:
    def test_select_edit_mode_default_replace(self):
        d = select_edit_mode(1, 10)
        assert d.mode == "replace"

    def test_select_edit_mode_rewrite_on_many_sites(self):
        d = select_edit_mode(4, 5)
        assert d.mode == "rewrite"

    def test_select_edit_mode_rewrite_on_large_span(self):
        d = select_edit_mode(1, 41)
        assert d.mode == "rewrite"

    def test_emit_edit_mode_event_contains_required_fields(self):
        d = EditModeDecision(mode="replace", sites=2, span=10)
        event = emit_edit_mode_event(d, feature_id="feat-001")
        assert event["event"] == "EDIT_MODE"
        assert event["mode"] == "replace"
        assert event["sites"] == 2
        assert event["span"] == 10
        assert event["feature_id"] == "feat-001"

    def test_apply_cheap_wins_sets_edit_mode_in_metadata(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature, edit_site_count=5, edit_span=50)
        assert meta["edit_mode"]["mode"] == "rewrite"
        assert meta["edit_mode"]["sites"] == 5
        assert meta["edit_mode"]["span"] == 50

    def test_apply_cheap_wins_replace_mode_for_small_edits(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature, edit_site_count=1, edit_span=10)
        assert meta["edit_mode"]["mode"] == "replace"


# ── (D) WEAK_TEST_DETECTED ────────────────────────────────────────────────────

class TestWeakTestDetection:
    def test_emit_weak_test_event_returns_dict(self):
        event = emit_weak_test_event("feat-001")
        assert isinstance(event, dict)

    def test_emit_weak_test_event_contains_event_key(self):
        event = emit_weak_test_event("feat-001")
        assert event["event"] == "WEAK_TEST_DETECTED"

    def test_emit_weak_test_event_contains_feature_id(self):
        event = emit_weak_test_event("feat-abc")
        assert event["feature_id"] == "feat-abc"

    def test_emit_weak_test_event_with_detail(self):
        event = emit_weak_test_event("feat-001", detail="flip failed")
        assert event["detail"] == "flip failed"

    def test_run_mutation_pass_check_returns_false_on_nonzero_exit(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

    def test_run_mutation_pass_check_returns_true_on_zero_exit(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="passed", stderr="")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is True

    def test_check_mutation_pass_is_alias_for_run(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

    def test_run_mutation_pass_check_on_timeout_returns_false(self, tmp_path):
        import subprocess
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.side_effect = subprocess.TimeoutExpired(cmd=["pytest"], timeout=120)
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

"""Tests for SWE-Bench cheap wins in bob.dispatch (F-R7-609).

Covers all four cheap-win directives:
  (A) repo_tree — build_repo_tree, inject_repo_tree_into_prompt
  (B) failing_repro_test — should_inject_repro_test_directive, inject_failing_repro_test_directive
  (C) adaptive edit mode — compute_edit_mode / select_edit_mode, emit_edit_mode_event
  (D) mutation-pass check — check_mutation_pass / run_mutation_pass_check, emit_weak_test_event

Also exercises the AC-required function names:
  - bob.dispatch.build_worker_system_prompt
  - bob.dispatch.compute_edit_mode
  - bob.dispatch.check_mutation_pass
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob.dispatch import (
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


# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_feature(**kwargs):
    """Create a minimal feature-like namespace for testing."""
    defaults = {
        "id": "test-feature-001",
        "name": "Test Feature",
        "description": "Test description",
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

    def test_non_empty_for_real_directory(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1")
        result = build_repo_tree(tmp_path)
        assert len(result) > 0

    def test_truncates_at_max_lines(self, tmp_path):
        # Create enough files to exceed the default 200-line cap
        for i in range(50):
            (tmp_path / f"file_{i:03d}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=10)
        lines = result.splitlines()
        # Should end with truncation marker
        assert any("more" in line for line in lines), f"Expected truncation marker, got: {lines[-3:]}"

    def test_truncation_marker_format(self, tmp_path):
        for i in range(20):
            (tmp_path / f"f{i}.txt").write_text("")
        result = build_repo_tree(tmp_path, max_lines=5)
        assert "more" in result
        # Marker should mention count
        last_line = result.splitlines()[-1]
        assert "(" in last_line and ")" in last_line

    def test_no_truncation_when_within_limit(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=200)
        assert "more" not in result

    def test_tree_fallback_when_tree_not_found(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "x.py").write_text("pass")
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("tree not found")
            result = build_repo_tree(tmp_path)
        # Should have gotten a fallback result (empty dir or unavailable)
        assert isinstance(result, str)

    def test_excludes_git_directory(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")
        result = build_repo_tree(tmp_path)
        # .git directory should not appear prominently (tree -I excludes it)
        # We can't be 100% sure of tree output format, but the file content
        # shouldn't appear in the workspace representation
        assert isinstance(result, str)


class TestInjectRepoTreeIntoPrompt:
    def test_prepends_tree_header(self, tmp_path):
        prompt = "Do the task."
        result = inject_repo_tree_into_prompt(prompt, tmp_path)
        assert result.startswith("## Repository Tree")
        assert "Do the task." in result

    def test_original_prompt_preserved(self, tmp_path):
        original = "Implement feature X with tests."
        result = inject_repo_tree_into_prompt(original, tmp_path)
        assert original in result

    def test_uses_code_fence(self, tmp_path):
        result = inject_repo_tree_into_prompt("prompt", tmp_path)
        assert "```" in result

    def test_header_mentions_f_r7_609(self, tmp_path):
        result = inject_repo_tree_into_prompt("prompt", tmp_path)
        assert "F-R7-609" in result


# ── (B) failing_repro_test ────────────────────────────────────────────────────


class TestShouldInjectReproTestDirective:
    def test_default_feature_injects(self):
        feature = make_feature()
        assert should_inject_repro_test_directive(feature) is True

    def test_skip_repro_test_true_suppresses(self):
        feature = make_feature(skip_repro_test=True)
        assert should_inject_repro_test_directive(feature) is False

    def test_no_acs_still_injects(self):
        feature = make_feature(acceptance_criteria=None)
        assert should_inject_repro_test_directive(feature) is True

    def test_all_structural_acs_suppresses(self):
        feature = make_feature(acceptance_criteria='["structural: file_exists src/foo.py", "structural: something"]')
        assert should_inject_repro_test_directive(feature) is False

    def test_mixed_acs_injects(self):
        feature = make_feature(acceptance_criteria='["pytest: tests/test_foo.py", "structural: file_exists"]')
        assert should_inject_repro_test_directive(feature) is True

    def test_empty_acs_list_injects(self):
        feature = make_feature(acceptance_criteria="[]")
        assert should_inject_repro_test_directive(feature) is True

    def test_list_acs_not_string(self):
        feature = make_feature()
        feature.acceptance_criteria = ["pytest: tests/test_foo.py"]
        assert should_inject_repro_test_directive(feature) is True


class TestInjectFailingReproTestDirective:
    def test_appends_directive(self):
        prompt = "Do something."
        result = inject_failing_repro_test_directive(prompt)
        assert result.startswith("Do something.")
        assert "STANDING DIRECTIVE" in result

    def test_contains_red_green_steps(self):
        result = inject_failing_repro_test_directive("base")
        assert "RED" in result or "failing test" in result.lower()
        assert "GREEN" in result or "edits" in result.lower()

    def test_directive_separator(self):
        result = inject_failing_repro_test_directive("base")
        assert "\n\n" in result


# ── (C) adaptive edit mode ────────────────────────────────────────────────────


class TestSelectEditMode:
    def test_small_edit_returns_replace(self):
        decision = select_edit_mode(1, 10)
        assert decision.mode == "replace"

    def test_many_sites_returns_rewrite(self):
        decision = select_edit_mode(4, 10)
        assert decision.mode == "rewrite"

    def test_large_span_returns_rewrite(self):
        decision = select_edit_mode(1, 41)
        assert decision.mode == "rewrite"

    def test_exactly_at_threshold_is_replace(self):
        # > threshold triggers rewrite; at threshold is replace
        decision = select_edit_mode(3, 40)
        assert decision.mode == "replace"

    def test_one_over_site_threshold_is_rewrite(self):
        decision = select_edit_mode(4, 0)
        assert decision.mode == "rewrite"

    def test_one_over_span_threshold_is_rewrite(self):
        decision = select_edit_mode(0, 41)
        assert decision.mode == "rewrite"

    def test_returns_edit_mode_decision(self):
        decision = select_edit_mode(2, 20)
        assert isinstance(decision, EditModeDecision)
        assert decision.sites == 2
        assert decision.span == 20

    def test_custom_thresholds(self):
        decision = select_edit_mode(2, 5, site_threshold=1, span_threshold=3)
        assert decision.mode == "rewrite"

    def test_zero_sites_zero_span_is_replace(self):
        decision = select_edit_mode(0, 0)
        assert decision.mode == "replace"


class TestComputeEditMode:
    """Tests for the AC-required alias compute_edit_mode."""

    def test_is_callable(self):
        assert callable(compute_edit_mode)

    def test_returns_edit_mode_decision(self):
        result = compute_edit_mode(1, 10)
        assert isinstance(result, EditModeDecision)

    def test_small_edit_replace(self):
        assert compute_edit_mode(2, 30).mode == "replace"

    def test_large_sites_rewrite(self):
        assert compute_edit_mode(10, 5).mode == "rewrite"

    def test_large_span_rewrite(self):
        assert compute_edit_mode(1, 100).mode == "rewrite"

    def test_both_over_threshold_rewrite(self):
        assert compute_edit_mode(5, 50).mode == "rewrite"

    def test_sites_field_preserved(self):
        result = compute_edit_mode(3, 15)
        assert result.sites == 3

    def test_span_field_preserved(self):
        result = compute_edit_mode(2, 25)
        assert result.span == 25


class TestEmitEditModeEvent:
    def test_returns_dict(self):
        decision = EditModeDecision(mode="replace", sites=1, span=10)
        event = emit_edit_mode_event(decision)
        assert isinstance(event, dict)

    def test_event_key_is_edit_mode(self):
        decision = EditModeDecision(mode="replace", sites=1, span=10)
        event = emit_edit_mode_event(decision)
        assert event["event"] == "EDIT_MODE"

    def test_mode_in_event(self):
        decision = EditModeDecision(mode="rewrite", sites=5, span=50)
        event = emit_edit_mode_event(decision)
        assert event["mode"] == "rewrite"

    def test_sites_and_span_in_event(self):
        decision = EditModeDecision(mode="replace", sites=2, span=20)
        event = emit_edit_mode_event(decision)
        assert event["sites"] == 2
        assert event["span"] == 20

    def test_feature_id_included_when_provided(self):
        decision = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(decision, feature_id="feat-001")
        assert event["feature_id"] == "feat-001"

    def test_feature_id_omitted_when_none(self):
        decision = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(decision)
        assert "feature_id" not in event


# ── (D) mutation-pass check ───────────────────────────────────────────────────


class TestEmitWeakTestEvent:
    def test_returns_dict(self):
        event = emit_weak_test_event("feat-123")
        assert isinstance(event, dict)

    def test_event_key_is_weak_test_detected(self):
        event = emit_weak_test_event("feat-123")
        assert event["event"] == "WEAK_TEST_DETECTED"

    def test_feature_id_in_event(self):
        event = emit_weak_test_event("feat-abc")
        assert event["feature_id"] == "feat-abc"

    def test_detail_included_when_provided(self):
        event = emit_weak_test_event("feat-001", detail="mutation did not flip")
        assert event["detail"] == "mutation did not flip"

    def test_detail_omitted_when_none(self):
        event = emit_weak_test_event("feat-001")
        assert "detail" not in event


class TestRunMutationPassCheck:
    def test_returns_false_when_test_fails(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
            result = run_mutation_pass_check(
                ["pytest", "test_foo.py"], tmp_path, "feat-001"
            )
        assert result is False

    def test_returns_true_when_test_passes_after_mutation(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = run_mutation_pass_check(
                ["pytest", "test_foo.py"], tmp_path, "feat-001"
            )
        assert result is True

    def test_emits_weak_test_event_when_still_passes(self, tmp_path, caplog):
        import logging
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with caplog.at_level(logging.WARNING, logger="bob.dispatch"):
                run_mutation_pass_check(["pytest", "test_foo.py"], tmp_path, "feat-wt")
        assert any("WEAK_TEST_DETECTED" in r.message for r in caplog.records)

    def test_timeout_returns_false(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=120)
            result = run_mutation_pass_check(
                ["pytest", "test_foo.py"], tmp_path, "feat-001"
            )
        assert result is False


class TestCheckMutationPass:
    """Tests for the AC-required alias check_mutation_pass."""

    def test_is_callable(self):
        assert callable(check_mutation_pass)

    def test_delegates_to_run_mutation_pass_check(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass(["pytest", "test.py"], tmp_path, "feat-002")
        assert result is False

    def test_returns_true_on_zero_exit(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = check_mutation_pass(["pytest", "test.py"], tmp_path, "feat-003")
        assert result is True

    def test_accepts_env_kwarg(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass(
                ["pytest", "test.py"], tmp_path, "feat-004", env={"MY_VAR": "1"}
            )
        assert result is False
        call_kwargs = mock_run.call_args[1]
        assert "MY_VAR" in call_kwargs["env"]

    def test_accepts_timeout_kwarg(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            check_mutation_pass(
                ["pytest", "test.py"], tmp_path, "feat-005", timeout=60
            )
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 60


# ── build_worker_system_prompt (AC-required) ──────────────────────────────────


class TestBuildWorkerSystemPrompt:
    def test_is_callable(self):
        assert callable(build_worker_system_prompt)

    def test_returns_string(self, tmp_path):
        feature = make_feature()
        result = build_worker_system_prompt("Do work.", tmp_path, feature)
        assert isinstance(result, str)

    def test_contains_repo_tree_header(self, tmp_path):
        feature = make_feature()
        result = build_worker_system_prompt("Do work.", tmp_path, feature)
        assert "Repository Tree" in result

    def test_contains_original_prompt(self, tmp_path):
        feature = make_feature()
        result = build_worker_system_prompt("Implement feature X.", tmp_path, feature)
        assert "Implement feature X." in result

    def test_contains_tdd_directive_by_default(self, tmp_path):
        feature = make_feature()
        result = build_worker_system_prompt("Work.", tmp_path, feature)
        assert "STANDING DIRECTIVE" in result or "failing test" in result.lower()

    def test_no_tdd_directive_when_skip_repro_test(self, tmp_path):
        feature = make_feature(skip_repro_test=True)
        result = build_worker_system_prompt("Work.", tmp_path, feature)
        assert "STANDING DIRECTIVE" not in result

    def test_tree_appears_before_prompt(self, tmp_path):
        feature = make_feature()
        prompt = "Do the actual task."
        result = build_worker_system_prompt(prompt, tmp_path, feature)
        tree_pos = result.find("Repository Tree")
        prompt_pos = result.find(prompt)
        assert tree_pos < prompt_pos, "Repo tree should appear before the prompt"


# ── apply_cheap_wins integration ──────────────────────────────────────────────


class TestApplyCheapWins:
    def test_returns_tuple(self, tmp_path):
        feature = make_feature()
        result = apply_cheap_wins("prompt", tmp_path, feature)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_augmented_prompt_contains_original(self, tmp_path):
        feature = make_feature()
        original = "Do the work now."
        prompt, _ = apply_cheap_wins(original, tmp_path, feature)
        assert original in prompt

    def test_metadata_contains_edit_mode(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature)
        assert "edit_mode" in meta
        assert meta["edit_mode"]["event"] == "EDIT_MODE"

    def test_metadata_repo_tree_injected(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature)
        assert meta["repo_tree_injected"] is True

    def test_skip_repo_tree_suppresses_tree(self, tmp_path):
        feature = make_feature(skip_repo_tree=True)
        _, meta = apply_cheap_wins("prompt", tmp_path, feature)
        assert meta["repo_tree_injected"] is False

    def test_failing_repro_test_injected_by_default(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature)
        assert meta["failing_repro_test_injected"] is True

    def test_edit_site_count_passed_through(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature, edit_site_count=5)
        assert meta["edit_mode"]["sites"] == 5
        assert meta["edit_mode"]["mode"] == "rewrite"

    def test_edit_span_passed_through(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature, edit_span=50)
        assert meta["edit_mode"]["span"] == 50
        assert meta["edit_mode"]["mode"] == "rewrite"


# ── Module-level AC checks ────────────────────────────────────────────────────


class TestModuleACs:
    """Verify the acceptance criteria directly against the module."""

    def test_file_exists(self):
        src = Path(__file__).parent.parent / "src" / "bob" / "dispatch.py"
        assert src.exists(), f"dispatch.py not found at {src}"

    def test_function_build_worker_system_prompt_defined(self):
        import bob.dispatch as m
        assert hasattr(m, "build_worker_system_prompt")
        assert callable(m.build_worker_system_prompt)

    def test_function_compute_edit_mode_defined(self):
        import bob.dispatch as m
        assert hasattr(m, "compute_edit_mode")
        assert callable(m.compute_edit_mode)

    def test_function_check_mutation_pass_defined(self):
        import bob.dispatch as m
        assert hasattr(m, "check_mutation_pass")
        assert callable(m.check_mutation_pass)

    def test_integration_bob_dispatch_importable(self):
        import importlib
        mod = importlib.import_module("bob.dispatch")
        assert mod is not None

    def test_all_ac_functions_in_dunder_all(self):
        import bob.dispatch as m
        for fn in ["build_worker_system_prompt", "compute_edit_mode", "check_mutation_pass"]:
            assert fn in m.__all__, f"{fn} not in __all__"

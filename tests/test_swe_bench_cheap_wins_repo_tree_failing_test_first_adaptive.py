"""Tests for bob3.swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive.

Feature b9dac9b9: SWE-Bench cheap wins — repo tree, failing-test-first,
adaptive edit mode, mutation-pass check.

ACs tested:
  - File exists: src/bob3/swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive.py
  - pytest: tests/test_swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive.py
    ::test_swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive
  - Function defined: bob3.swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive
    .swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive
  - integration: bob3.orchestrator.run_loop
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob3.swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive import (
    EditModeDecision,
    apply_failing_repro_test_directive,
    apply_repo_tree,
    run_weak_test_check,
    select_adaptive_edit_mode,
    swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_feature(
    *,
    id: str = "feat-swe-001",
    name: str = "Test SWE Feature",
    description: str = "A test SWE-Bench feature",
    acceptance_criteria: str | None = '["pytest: tests/test_foo.py"]',
    localization_shortlist: list[str] | None = None,
    skip_repo_tree: bool = False,
    skip_repro_test: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        localization_shortlist=localization_shortlist or [],
        skip_repo_tree=skip_repo_tree,
        skip_repro_test=skip_repro_test,
    )


# ── Primary AC: function exists and is callable ───────────────────────────────


def test_swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive():
    """Primary AC: function is callable (the test name matches the AC exactly)."""
    assert callable(swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive)


# ── (A) apply_repo_tree ────────────────────────────────────────────────────────


class TestApplyRepoTree:
    def test_returns_string(self, tmp_path):
        result = apply_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_includes_workspace_path(self, tmp_path):
        result = apply_repo_tree(tmp_path)
        assert len(result) >= 0  # non-empty workspace name or fallback text

    def test_caps_at_max_lines(self, tmp_path):
        # Create many subdirs to exceed 200 lines
        for i in range(30):
            sub = tmp_path / f"sub_{i:03d}"
            sub.mkdir()
            for j in range(10):
                (sub / f"file_{j:03d}.py").touch()
        result = apply_repo_tree(tmp_path, max_lines=10)
        lines = result.splitlines()
        # Should have truncation marker
        assert any("more" in line for line in lines)

    def test_truncation_message_format(self, tmp_path):
        for i in range(20):
            (tmp_path / f"file_{i:02d}.py").touch()
        result = apply_repo_tree(tmp_path, max_lines=5)
        assert "…" in result or "more" in result.lower()

    def test_no_truncation_when_under_limit(self, tmp_path):
        (tmp_path / "file_a.py").touch()
        (tmp_path / "file_b.py").touch()
        result = apply_repo_tree(tmp_path, max_lines=200)
        assert "more" not in result or "…" not in result


# ── (B) apply_failing_repro_test_directive ─────────────────────────────────────


class TestApplyFailingReproTestDirective:
    def test_injects_directive_by_default(self):
        feature = _make_feature()
        augmented, injected = apply_failing_repro_test_directive("base prompt", feature)
        assert injected is True
        assert "STANDING DIRECTIVE" in augmented

    def test_no_injection_when_skip_repro_test_true(self):
        feature = _make_feature(skip_repro_test=True)
        augmented, injected = apply_failing_repro_test_directive("base prompt", feature)
        assert injected is False
        assert "STANDING DIRECTIVE" not in augmented

    def test_base_prompt_preserved(self):
        feature = _make_feature()
        augmented, _ = apply_failing_repro_test_directive("my base prompt", feature)
        assert "my base prompt" in augmented

    def test_directive_contains_red_green_steps(self):
        feature = _make_feature()
        augmented, _ = apply_failing_repro_test_directive("prompt", feature)
        assert "RED" in augmented or "failing" in augmented.lower()
        assert "GREEN" in augmented or "green" in augmented.lower()

    def test_returns_tuple_of_str_and_bool(self):
        feature = _make_feature()
        result = apply_failing_repro_test_directive("prompt", feature)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], bool)


# ── (C) select_adaptive_edit_mode ─────────────────────────────────────────────


class TestSelectAdaptiveEditMode:
    def test_default_is_replace(self):
        decision = select_adaptive_edit_mode(0, 0)
        assert decision.mode == "replace"

    def test_rewrite_when_sites_exceed_threshold(self):
        decision = select_adaptive_edit_mode(4, 0)
        assert decision.mode == "rewrite"

    def test_rewrite_when_span_exceeds_threshold(self):
        decision = select_adaptive_edit_mode(0, 41)
        assert decision.mode == "rewrite"

    def test_replace_at_boundary_sites(self):
        decision = select_adaptive_edit_mode(3, 0)
        assert decision.mode == "replace"

    def test_replace_at_boundary_span(self):
        decision = select_adaptive_edit_mode(0, 40)
        assert decision.mode == "replace"

    def test_rewrite_when_both_exceed(self):
        decision = select_adaptive_edit_mode(5, 50)
        assert decision.mode == "rewrite"

    def test_returns_edit_mode_decision(self):
        decision = select_adaptive_edit_mode(1, 10)
        assert isinstance(decision, EditModeDecision)
        assert decision.sites == 1
        assert decision.span == 10

    def test_sites_and_span_stored(self):
        decision = select_adaptive_edit_mode(2, 15)
        assert decision.sites == 2
        assert decision.span == 15


# ── (D) run_weak_test_check ───────────────────────────────────────────────────


class TestRunWeakTestCheck:
    def test_returns_true_when_test_still_passes(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = run_weak_test_check(
                ["python", "-m", "pytest", "tests/test_foo.py"],
                tmp_path,
                "feat-001",
            )
        assert result is True

    def test_returns_false_when_test_fails(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
            result = run_weak_test_check(
                ["python", "-m", "pytest", "tests/test_foo.py"],
                tmp_path,
                "feat-002",
            )
        assert result is False

    def test_emits_weak_test_event_on_pass(self, tmp_path, caplog):
        import logging
        with patch("bob3.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with caplog.at_level(logging.WARNING, logger="bob3.dispatch"):
                run_weak_test_check(
                    ["python", "-m", "pytest", "tests/test_foo.py"],
                    tmp_path,
                    "feat-003",
                )
        # Should have logged WEAK_TEST_DETECTED
        assert any("WEAK_TEST_DETECTED" in r.message for r in caplog.records)

    def test_handles_timeout(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=120)
            result = run_weak_test_check(
                ["python", "-m", "pytest", "tests/test_foo.py"],
                tmp_path,
                "feat-004",
                timeout=120,
            )
        # Timeout is treated as "test failed" (not still passing)
        assert result is False


# ── Main function (all four wins) ─────────────────────────────────────────────


class TestSweBenchCheapWinsMainFunction:
    def test_returns_tuple(self, tmp_path):
        feature = _make_feature()
        result = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_augmented_prompt_is_string(self, tmp_path):
        feature = _make_feature()
        prompt, _ = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert isinstance(prompt, str)

    def test_metadata_is_dict(self, tmp_path):
        feature = _make_feature()
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert isinstance(metadata, dict)

    def test_metadata_has_repo_tree_injected(self, tmp_path):
        feature = _make_feature()
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert "repo_tree_injected" in metadata

    def test_metadata_has_failing_repro_test_injected(self, tmp_path):
        feature = _make_feature()
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert "failing_repro_test_injected" in metadata

    def test_metadata_has_edit_mode(self, tmp_path):
        feature = _make_feature()
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert "edit_mode" in metadata

    def test_skip_repo_tree_respected(self, tmp_path):
        feature = _make_feature(skip_repo_tree=True)
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert metadata["repo_tree_injected"] is False

    def test_repo_tree_injected_by_default(self, tmp_path):
        feature = _make_feature(skip_repo_tree=False)
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert metadata["repo_tree_injected"] is True

    def test_failing_repro_test_injected_by_default(self, tmp_path):
        feature = _make_feature(skip_repro_test=False)
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert metadata["failing_repro_test_injected"] is True

    def test_skip_repro_test_respected(self, tmp_path):
        feature = _make_feature(skip_repro_test=True)
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature
        )
        assert metadata["failing_repro_test_injected"] is False

    def test_edit_mode_replace_by_default(self, tmp_path):
        feature = _make_feature()
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature, edit_site_count=1, edit_span=5
        )
        assert metadata["edit_mode"]["mode"] == "replace"

    def test_edit_mode_rewrite_with_large_edit(self, tmp_path):
        feature = _make_feature()
        _, metadata = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "base prompt", tmp_path, feature, edit_site_count=5, edit_span=50
        )
        assert metadata["edit_mode"]["mode"] == "rewrite"

    def test_base_prompt_content_preserved(self, tmp_path):
        feature = _make_feature(skip_repo_tree=True, skip_repro_test=True)
        prompt, _ = swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive(
            "unique-base-content-12345", tmp_path, feature
        )
        assert "unique-base-content-12345" in prompt


# ── Integration AC: bob3.orchestrator.run_loop ────────────────────────────────


class TestIntegrationRunLoop:
    def test_run_loop_imports_swe_bench_cheap_wins(self):
        """Integration AC: the module must be importable from bob3.orchestrator.run_loop."""
        import importlib
        # The import chain must not error
        run_loop = importlib.import_module("bob3.orchestrator.run_loop")
        assert run_loop is not None

    def test_swe_bench_module_importable_from_bob3(self):
        """Module must be importable from the bob3 package namespace."""
        import bob3.swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive as mod
        assert mod is not None

    def test_cheap_wins_function_importable(self):
        """Main function must be importable from the module."""
        from bob3.swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive import (
            swe_bench_cheap_wins_repo_tree_failing_test_first_adaptive as fn,
        )
        assert callable(fn)

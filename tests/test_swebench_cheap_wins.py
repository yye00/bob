"""Tests for SWE-Bench cheap wins in bob.dispatch (F-R7-609).

Covers the four leaderboard-validated brownfield directives:
  (A) repo_tree           — build_repo_tree / inject_repo_tree_into_prompt
  (B) failing_repro_test  — should_inject_repro_test_directive / injector
  (C) adaptive EDIT_MODE  — select_edit_mode / mutation thresholds
  (D) mutation-pass check — mutation_pass_check / WEAK_TEST_DETECTED

Plus the combined apply_cheap_wins entry point (integration: bob.dispatch).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob.dispatch import (
    EditModeDecision,
    apply_cheap_wins,
    build_repo_tree,
    emit_edit_mode_event,
    emit_weak_test_event,
    inject_failing_repro_test_directive,
    inject_repo_tree_into_prompt,
    mutation_pass_check,
    run_mutation_pass_check,
    select_edit_mode,
    should_inject_repro_test_directive,
)


def make_feature(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": "feat-001",
        "name": "Test Feature",
        "description": "desc",
        "acceptance_criteria": None,
        "skip_repro_test": False,
        "skip_repo_tree": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── (A) repo_tree ─────────────────────────────────────────────────────────────


class TestRepoTree:
    def test_build_repo_tree_returns_string(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)
        assert "a.py" in result

    def test_build_repo_tree_caps_at_max_lines(self):
        many = [f"line{i}" for i in range(500)]
        fake = MagicMock()
        fake.stdout = "\n".join(many)
        with patch("bob.dispatch.subprocess.run", return_value=fake):
            result = build_repo_tree("/some/ws", max_lines=10)
        lines = result.splitlines()
        assert len(lines) == 11  # 10 + trailer
        assert lines[-1] == "… (490 more)"

    def test_inject_repo_tree_prepends_block(self, tmp_path):
        (tmp_path / "b.py").write_text("y = 2\n")
        out = inject_repo_tree_into_prompt("BASE PROMPT", tmp_path)
        assert out.endswith("BASE PROMPT")
        assert "Repository Tree" in out


# ── (B) failing_repro_test ────────────────────────────────────────────────────


class TestFailingReproTest:
    def test_default_injects(self):
        assert should_inject_repro_test_directive(make_feature()) is True

    def test_skip_flag_disables(self):
        assert should_inject_repro_test_directive(make_feature(skip_repro_test=True)) is False

    def test_all_structural_acs_disables(self):
        feat = make_feature(acceptance_criteria=["file_exists: src/x.py"])
        assert should_inject_repro_test_directive(feat) is False

    def test_mixed_acs_still_injects(self):
        feat = make_feature(acceptance_criteria=["file_exists: x", "pytest: tests/t.py"])
        assert should_inject_repro_test_directive(feat) is True

    def test_injector_appends_directive(self):
        out = inject_failing_repro_test_directive("PROMPT")
        assert out.startswith("PROMPT")
        assert "STANDING DIRECTIVE" in out


# ── (C) adaptive EDIT_MODE ────────────────────────────────────────────────────


class TestEditMode:
    def test_small_edit_uses_replace(self):
        d = select_edit_mode(1, 5)
        assert isinstance(d, EditModeDecision)
        assert d.mode == "replace"

    def test_many_sites_switch_to_rewrite(self):
        assert select_edit_mode(4, 5).mode == "rewrite"

    def test_large_span_switch_to_rewrite(self):
        assert select_edit_mode(1, 41).mode == "rewrite"

    def test_at_thresholds_stays_replace(self):
        assert select_edit_mode(3, 40).mode == "replace"

    def test_emit_event_shape(self):
        event = emit_edit_mode_event(select_edit_mode(4, 50), feature_id="feat-x")
        assert event["event"] == "EDIT_MODE"
        assert event["mode"] == "rewrite"
        assert event["sites"] == 4
        assert event["span"] == 50
        assert event["feature_id"] == "feat-x"


# ── (D) mutation-pass check ───────────────────────────────────────────────────


class TestMutationPassCheck:
    def test_still_passes_flags_weak_test(self, tmp_path):
        fake = MagicMock()
        fake.returncode = 0
        with patch("bob.dispatch.subprocess.run", return_value=fake):
            result = mutation_pass_check(["pytest", "x"], tmp_path, "feat-1")
        assert result is True

    def test_mutation_flips_result_is_ok(self, tmp_path):
        fake = MagicMock()
        fake.returncode = 1
        with patch("bob.dispatch.subprocess.run", return_value=fake):
            result = mutation_pass_check(["pytest", "x"], tmp_path, "feat-1")
        assert result is False

    def test_delegates_to_run_mutation_pass_check(self, tmp_path):
        with patch("bob.dispatch.run_mutation_pass_check", return_value=True) as m:
            assert mutation_pass_check(["pytest"], tmp_path, "feat-1") is True
        m.assert_called_once()

    def test_emit_weak_test_event_shape(self):
        event = emit_weak_test_event("feat-9", detail="under-specified")
        assert event["event"] == "WEAK_TEST_DETECTED"
        assert event["feature_id"] == "feat-9"
        assert event["detail"] == "under-specified"


# ── integration: apply_cheap_wins ─────────────────────────────────────────────


class TestApplyCheapWins:
    def test_applies_all_wins(self, tmp_path):
        (tmp_path / "c.py").write_text("z = 3\n")
        feat = make_feature(id="feat-int")
        prompt, meta = apply_cheap_wins("BASE", tmp_path, feat, edit_site_count=4, edit_span=50)
        assert meta["repo_tree_injected"] is True
        assert meta["failing_repro_test_injected"] is True
        assert meta["edit_mode"]["mode"] == "rewrite"
        assert "Repository Tree" in prompt
        assert "STANDING DIRECTIVE" in prompt

    def test_respects_skip_toggles(self, tmp_path):
        feat = make_feature(skip_repo_tree=True, skip_repro_test=True)
        prompt, meta = apply_cheap_wins("BASE", tmp_path, feat)
        assert meta["repo_tree_injected"] is False
        assert meta["failing_repro_test_injected"] is False
        assert "Repository Tree" not in prompt

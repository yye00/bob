"""Tests for SWE-Bench directives in bob.dispatch (F-R7-609).

Covers the four cheap-win directives:
  (A) repo_tree — inject repo tree into worker prompt
  (B) failing_repro_test — TDD standing directive
  (C) adaptive EDIT_MODE — string-replace vs whole-file rewrite
  (D) WEAK_TEST_DETECTED — mutation-pass check telemetry

Focus: directive injection logic, toggles, and event structure.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob.dispatch import (
    EditModeDecision,
    apply_cheap_wins,
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
        "id": "feat-directive-001",
        "name": "Directive Test Feature",
        "acceptance_criteria": '["pytest: tests/test_foo.py"]',
        "skip_repro_test": False,
        "skip_repo_tree": False,
        "localization_shortlist": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── (A) repo_tree directive ───────────────────────────────────────────────────


class TestRepoTreeDirective:
    def test_inject_prepends_to_prompt(self, tmp_path):
        prompt = "Fix the bug."
        result = inject_repo_tree_into_prompt(prompt, tmp_path)
        assert result.index("Repository Tree") < result.index("Fix the bug.")

    def test_inject_wraps_tree_in_code_fence(self, tmp_path):
        result = inject_repo_tree_into_prompt("Do work.", tmp_path)
        assert "```" in result

    def test_inject_labels_feature(self, tmp_path):
        result = inject_repo_tree_into_prompt("Do work.", tmp_path)
        assert "F-R7-609" in result

    def test_skip_repo_tree_suppresses_injection(self, tmp_path):
        feature = make_feature(skip_repo_tree=True)
        _, meta = apply_cheap_wins("prompt", tmp_path, feature)
        assert meta["repo_tree_injected"] is False

    def test_repo_tree_enabled_by_default(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature)
        assert meta["repo_tree_injected"] is True


# ── (B) failing_repro_test directive ─────────────────────────────────────────


class TestFailingReproTestDirective:
    def test_directive_injected_for_default_feature(self):
        feature = make_feature()
        assert should_inject_repro_test_directive(feature) is True

    def test_directive_suppressed_when_skip_true(self):
        feature = make_feature(skip_repro_test=True)
        assert should_inject_repro_test_directive(feature) is False

    def test_directive_text_contains_red_step(self):
        result = inject_failing_repro_test_directive("base prompt")
        assert "RED" in result

    def test_directive_text_contains_green_step(self):
        result = inject_failing_repro_test_directive("base prompt")
        assert "GREEN" in result

    def test_directive_is_standing_directive(self):
        result = inject_failing_repro_test_directive("base prompt")
        assert "STANDING DIRECTIVE" in result

    def test_directive_appended_after_base_prompt(self):
        base = "Some base prompt text."
        result = inject_failing_repro_test_directive(base)
        assert result.startswith(base)

    def test_all_structural_acs_suppress_directive(self):
        feature = make_feature(acceptance_criteria='["structural: foo", "structural: bar"]')
        assert should_inject_repro_test_directive(feature) is False

    def test_pytest_ac_enables_directive(self):
        feature = make_feature(acceptance_criteria='["pytest: tests/test_x.py"]')
        assert should_inject_repro_test_directive(feature) is True

    def test_build_worker_system_prompt_includes_directive(self, tmp_path):
        feature = make_feature()
        result = build_worker_system_prompt("Do work.", tmp_path, feature)
        assert "STANDING DIRECTIVE" in result

    def test_build_worker_system_prompt_skips_directive_when_requested(self, tmp_path):
        feature = make_feature(skip_repro_test=True)
        result = build_worker_system_prompt("Do work.", tmp_path, feature)
        assert "STANDING DIRECTIVE" not in result


# ── (C) EDIT_MODE directive ───────────────────────────────────────────────────


class TestEditModeDirective:
    def test_default_mode_is_replace(self):
        decision = select_edit_mode(0, 0)
        assert decision.mode == "replace"

    def test_many_sites_triggers_rewrite(self):
        decision = select_edit_mode(4, 0)
        assert decision.mode == "rewrite"

    def test_large_span_triggers_rewrite(self):
        decision = select_edit_mode(0, 41)
        assert decision.mode == "rewrite"

    def test_threshold_boundary_stays_replace(self):
        decision = select_edit_mode(3, 40)
        assert decision.mode == "replace"

    def test_compute_edit_mode_alias(self):
        d1 = select_edit_mode(2, 20)
        d2 = compute_edit_mode(2, 20)
        assert d1.mode == d2.mode
        assert d1.sites == d2.sites
        assert d1.span == d2.span

    def test_edit_mode_event_structure(self):
        decision = EditModeDecision(mode="replace", sites=1, span=10)
        event = emit_edit_mode_event(decision)
        assert event["event"] == "EDIT_MODE"
        assert event["mode"] == "replace"
        assert event["sites"] == 1
        assert event["span"] == 10

    def test_edit_mode_event_with_feature_id(self):
        decision = EditModeDecision(mode="rewrite", sites=5, span=50)
        event = emit_edit_mode_event(decision, feature_id="f-001")
        assert event["feature_id"] == "f-001"

    def test_apply_cheap_wins_records_edit_mode(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature, edit_site_count=5)
        assert meta["edit_mode"]["mode"] == "rewrite"

    def test_apply_cheap_wins_records_sites_count(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature, edit_site_count=2, edit_span=10)
        assert meta["edit_mode"]["sites"] == 2

    def test_apply_cheap_wins_records_span(self, tmp_path):
        feature = make_feature()
        _, meta = apply_cheap_wins("prompt", tmp_path, feature, edit_site_count=1, edit_span=50)
        assert meta["edit_mode"]["span"] == 50


# ── (D) WEAK_TEST_DETECTED directive ─────────────────────────────────────────


class TestWeakTestDetectedDirective:
    def test_event_key_is_correct(self):
        event = emit_weak_test_event("feat-001")
        assert event["event"] == "WEAK_TEST_DETECTED"

    def test_event_contains_feature_id(self):
        event = emit_weak_test_event("feat-xyz")
        assert event["feature_id"] == "feat-xyz"

    def test_event_detail_optional(self):
        event = emit_weak_test_event("feat-001")
        assert "detail" not in event

    def test_event_detail_included_when_provided(self):
        event = emit_weak_test_event("feat-001", detail="mutation didn't flip")
        assert event["detail"] == "mutation didn't flip"

    def test_mutation_check_returns_true_when_test_still_passes(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "f-001")
        assert result is True

    def test_mutation_check_returns_false_when_test_fails(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "f-001")
        assert result is False

    def test_check_mutation_pass_alias(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass(["pytest", "test.py"], tmp_path, "f-001")
        assert result is False

    def test_mutation_check_emits_warning_on_weak_test(self, tmp_path, caplog):
        import logging
        with patch("bob.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with caplog.at_level(logging.WARNING, logger="bob.dispatch"):
                run_mutation_pass_check(["pytest", "test.py"], tmp_path, "f-001")
        assert any("WEAK_TEST_DETECTED" in r.message for r in caplog.records)

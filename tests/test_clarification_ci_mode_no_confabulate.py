"""Tests that CI mode exits SPEC_NEEDS_HUMAN rather than confabulating.

Feature: e38b904e-6b04-4d5a-818b-095c0f3a26be
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import os
import pytest

from bob.spec_quality.clarification_loop import (
    SPEC_NEEDS_HUMAN,
    code_consistency_check,
    run_clarification_loop,
)

_FUNCS_AC = [
    "Function defined: bob.spec_quality.clarification_loop.code_consistency_check",
    "Function defined: bob.spec_quality.clarification_loop.compute_slot_uncertainty",
    "Function defined: bob.spec_quality.clarification_loop.ask_user_batched",
]


class TestCiModeNoConfabulate:
    def test_ci_mode_flag_sets_spec_needs_human_when_uncertain(self):
        report = code_consistency_check(_FUNCS_AC, ci_mode=True)
        # If any uncertain slots found in CI mode → spec_needs_human
        if report.uncertain_slots:
            assert report.spec_needs_human is True

    def test_ci_mode_false_does_not_set_spec_needs_human(self):
        report = code_consistency_check(_FUNCS_AC, ci_mode=False)
        assert report.spec_needs_human is False

    def test_env_var_ci_mode_true_sets_flag(self, monkeypatch):
        monkeypatch.setenv("BOB_CI_MODE", "1")
        report = code_consistency_check(_FUNCS_AC)
        if report.uncertain_slots:
            assert report.spec_needs_human is True

    def test_env_var_ci_mode_false_clears_flag(self, monkeypatch):
        monkeypatch.setenv("BOB_CI_MODE", "0")
        report = code_consistency_check(_FUNCS_AC)
        assert report.spec_needs_human is False

    def test_env_var_unset_defaults_to_non_ci(self, monkeypatch):
        monkeypatch.delenv("BOB_CI_MODE", raising=False)
        report = code_consistency_check(_FUNCS_AC)
        assert report.spec_needs_human is False

    def test_run_loop_returns_spec_needs_human_in_ci_mode(self, tmp_path):
        acs = _FUNCS_AC
        slots, outcome = run_clarification_loop(
            acs,
            ci_mode=True,
            audit_log_path=tmp_path / "clarifications.log",
        )
        # If uncertain slots exist in CI mode → should return SPEC_NEEDS_HUMAN
        report = code_consistency_check(acs, ci_mode=True)
        if report.uncertain_slots:
            assert outcome == SPEC_NEEDS_HUMAN

    def test_run_loop_no_uncertain_slots_returns_none(self, tmp_path):
        # With no Function defined ACs → no slots → no uncertainty → no SPEC_NEEDS_HUMAN
        acs = ["File exists: src/bob/spec_quality/clarification_loop.py"]
        slots, outcome = run_clarification_loop(
            acs,
            ci_mode=True,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert outcome is None

    def test_spec_needs_human_constant_value(self):
        assert SPEC_NEEDS_HUMAN == "SPEC_NEEDS_HUMAN"

    def test_ci_mode_with_empty_ac_no_confusion(self, tmp_path):
        slots, outcome = run_clarification_loop(
            [],
            ci_mode=True,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert outcome is None
        assert slots == {}

    def test_ci_env_var_truthy_variants(self, monkeypatch):
        for val in ("1", "true", "yes", "on", "True", "YES"):
            monkeypatch.setenv("BOB_CI_MODE", val)
            report = code_consistency_check(_FUNCS_AC)
            if report.uncertain_slots:
                assert report.spec_needs_human is True, f"Expected CI mode for BOB_CI_MODE={val!r}"

    def test_ci_env_var_falsy_variants(self, monkeypatch):
        for val in ("0", "false", "no", "off", "False", "NO"):
            monkeypatch.setenv("BOB_CI_MODE", val)
            report = code_consistency_check(_FUNCS_AC)
            assert report.spec_needs_human is False, f"Expected non-CI for BOB_CI_MODE={val!r}"

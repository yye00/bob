"""Tests for failing_repro_test directive in bob.dispatch (F-R7-609).

Covers should_inject_repro_test_directive, inject_failing_repro_test_directive,
and apply_repro_test_directive. Anthropic +pp prompt addendum: TDD standing
directive for all non-structural ACs.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bob.dispatch import (
    apply_repro_test_directive,
    inject_failing_repro_test_directive,
    should_inject_repro_test_directive,
)


def make_feature(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": "feat-repro-001",
        "name": "Repro Test Feature",
        "acceptance_criteria": '["pytest: tests/test_foo.py"]',
        "skip_repro_test": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestShouldInjectReproTestDirective:
    def test_returns_true_by_default(self):
        feature = make_feature()
        assert should_inject_repro_test_directive(feature) is True

    def test_skip_repro_test_true_returns_false(self):
        feature = make_feature(skip_repro_test=True)
        assert should_inject_repro_test_directive(feature) is False

    def test_skip_repro_test_false_returns_true(self):
        feature = make_feature(skip_repro_test=False)
        assert should_inject_repro_test_directive(feature) is True

    def test_none_acceptance_criteria_returns_true(self):
        feature = make_feature(acceptance_criteria=None)
        result = should_inject_repro_test_directive(feature)
        assert result is True

    def test_empty_acceptance_criteria_returns_true(self):
        feature = make_feature(acceptance_criteria="[]")
        result = should_inject_repro_test_directive(feature)
        assert result is True

    def test_pytest_acs_returns_true(self):
        feature = make_feature(acceptance_criteria='["pytest: tests/test_x.py"]')
        assert should_inject_repro_test_directive(feature) is True

    def test_structural_acs_only_returns_false(self):
        feature = make_feature(
            acceptance_criteria='["structural: some file structure check", "structural: another"]'
        )
        result = should_inject_repro_test_directive(feature)
        assert result is False

    def test_mixed_acs_with_non_structural_returns_true(self):
        feature = make_feature(
            acceptance_criteria='["structural: check", "pytest: tests/test_foo.py"]'
        )
        result = should_inject_repro_test_directive(feature)
        assert result is True

    def test_malformed_json_acs_returns_true(self):
        feature = make_feature(acceptance_criteria="{not valid json}")
        result = should_inject_repro_test_directive(feature)
        assert result is True

    def test_returns_bool_type(self):
        feature = make_feature()
        result = should_inject_repro_test_directive(feature)
        assert isinstance(result, bool)

    def test_feature_without_skip_repro_test_attr_returns_true(self):
        feature = SimpleNamespace(acceptance_criteria='["pytest: tests/test_foo.py"]')
        result = should_inject_repro_test_directive(feature)
        assert result is True


class TestInjectFailingReproTestDirective:
    def test_returns_string(self):
        result = inject_failing_repro_test_directive("my prompt")
        assert isinstance(result, str)

    def test_original_prompt_preserved(self):
        result = inject_failing_repro_test_directive("my task")
        assert "my task" in result

    def test_standing_directive_header_included(self):
        result = inject_failing_repro_test_directive("prompt")
        assert "STANDING DIRECTIVE" in result

    def test_tdd_steps_included(self):
        result = inject_failing_repro_test_directive("prompt")
        assert "RED" in result or "failing test" in result.lower()

    def test_green_step_mentioned(self):
        result = inject_failing_repro_test_directive("prompt")
        assert "GREEN" in result or "passes" in result.lower()

    def test_directive_appended_not_prepended(self):
        result = inject_failing_repro_test_directive("original")
        prompt_pos = result.find("original")
        directive_pos = result.find("STANDING DIRECTIVE")
        assert prompt_pos < directive_pos

    def test_empty_prompt_returns_nonempty_result(self):
        result = inject_failing_repro_test_directive("")
        assert len(result) > 0

    def test_result_longer_than_input(self):
        prompt = "do work"
        result = inject_failing_repro_test_directive(prompt)
        assert len(result) > len(prompt)


class TestApplyReproTestDirective:
    def test_injects_when_not_skipped(self):
        feature = make_feature(skip_repro_test=False)
        result = apply_repro_test_directive("prompt", feature)
        assert "STANDING DIRECTIVE" in result

    def test_skips_when_skip_repro_test_true(self):
        feature = make_feature(skip_repro_test=True)
        result = apply_repro_test_directive("prompt", feature)
        assert result == "prompt"

    def test_returns_string(self):
        feature = make_feature()
        result = apply_repro_test_directive("prompt", feature)
        assert isinstance(result, str)

    def test_returns_original_prompt_unchanged_when_skipped(self):
        feature = make_feature(skip_repro_test=True)
        original = "original prompt text"
        result = apply_repro_test_directive(original, feature)
        assert result == original

    def test_structural_only_acs_skips_injection(self):
        feature = make_feature(
            skip_repro_test=False,
            acceptance_criteria='["structural: check file exists", "structural: verify grep"]',
        )
        result = apply_repro_test_directive("prompt", feature)
        assert result == "prompt"

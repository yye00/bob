"""Tests for bob.synthesis.canonical_ac_emitter.

Covers all acceptance criteria for feature c3e695fb-9154-4a83-9d9d-feb58a8dac32:
- validate_canonical_form returns non-canonical ACs
- emit_negative_path_ac output passes validate_canonical_form (empty non-canonical set)
- synthesise_with_canonical_gate skips persist after 3 failed retries
- canonical-form input proceeds without retry (no regression)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bob.synthesis.canonical_ac_emitter import (
    SYNTHESIS_BLOCKED_STATUS,
    SynthesisResult,
    emit_negative_path_ac,
    synthesise_with_canonical_gate,
    validate_canonical_form,
)


# ---------------------------------------------------------------------------
# validate_canonical_form
# ---------------------------------------------------------------------------


class TestValidateCanonicalForm:
    """Tests for validate_canonical_form."""

    def test_prose_ac_returns_in_non_canonical_subset(self):
        prose_acs = [
            "FailureClass enum: the system should handle it AND classify_failure() != unknown",
            "The module works correctly for all inputs",
            "Handles edge cases gracefully",
        ]
        result = validate_canonical_form(prose_acs)
        assert len(result) == 3
        assert prose_acs[0] in result
        assert prose_acs[1] in result
        assert prose_acs[2] in result

    def test_file_exists_is_canonical(self):
        acs = ["File exists: src/bob/synthesis/canonical_ac_emitter.py"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_function_defined_is_canonical(self):
        acs = ["Function defined: bob.synthesis.canonical_ac_emitter.validate_canonical_form"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_pytest_is_canonical(self):
        acs = ["pytest: tests/test_canonical_ac_emitter.py"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_integration_is_canonical(self):
        acs = ["integration: bob.orchestrator.path_finding_retry.research_strategies"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_behavior_when_is_canonical(self):
        acs = ["behavior: validate_canonical_form returns empty list when all ACs are canonical"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_class_defined_is_canonical(self):
        acs = ["Class defined: bob.synthesis.canonical_ac_emitter.SynthesisResult"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_mixed_list_returns_only_non_canonical(self):
        acs = [
            "File exists: src/foo.py",
            "This is a prose criterion that does not match",
            "pytest: tests/test_foo.py",
            "Another vague requirement without structure",
        ]
        result = validate_canonical_form(acs)
        assert len(result) == 2
        assert "This is a prose criterion that does not match" in result
        assert "Another vague requirement without structure" in result

    def test_empty_list_returns_empty(self):
        assert validate_canonical_form([]) == []

    def test_all_canonical_returns_empty(self):
        acs = [
            "File exists: src/bob/synthesis/canonical_ac_emitter.py",
            "Function defined: bob.synthesis.canonical_ac_emitter.validate_canonical_form",
            "pytest: tests/test_canonical_ac_emitter.py",
            "behavior: synthesise_with_canonical_gate skips persist when retries exhausted",
        ]
        result = validate_canonical_form(acs)
        assert result == []

    def test_case_insensitive_file_exists(self):
        acs = ["file exists: src/foo.py"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_case_insensitive_function_defined(self):
        acs = ["FUNCTION DEFINED: bob.foo.bar"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_case_insensitive_pytest(self):
        acs = ["PYTEST: tests/test_foo.py"]
        result = validate_canonical_form(acs)
        assert result == []

    def test_behavior_without_when_is_not_canonical(self):
        # behavior: prefix without 'when' clause should fail
        acs = ["behavior: the system handles errors gracefully"]
        result = validate_canonical_form(acs)
        assert len(result) == 1

    def test_whitespace_stripped_before_matching(self):
        acs = ["  File exists: src/foo.py  "]
        result = validate_canonical_form(acs)
        assert result == []


# ---------------------------------------------------------------------------
# emit_negative_path_ac
# ---------------------------------------------------------------------------


class TestEmitNegativePathAc:
    """Tests for emit_negative_path_ac."""

    def test_output_passes_validate_canonical_form(self):
        ac = emit_negative_path_ac("canonical_ac_emitter validation")
        non_canonical = validate_canonical_form([ac])
        assert non_canonical == [], (
            f"emit_negative_path_ac output should be canonical but got: {ac!r}"
        )

    def test_output_contains_error_or_failure_keyword(self):
        ac = emit_negative_path_ac("feature synthesis gate")
        lower = ac.lower()
        has_error_kw = any(kw in lower for kw in ("error", "failure", "invalid", "fail"))
        assert has_error_kw, f"Expected error/failure keyword in: {ac!r}"

    def test_output_uses_behavior_prefix(self):
        ac = emit_negative_path_ac("some feature")
        assert ac.startswith("behavior:"), f"Expected 'behavior:' prefix, got: {ac!r}"

    def test_feature_topic_incorporated(self):
        ac = emit_negative_path_ac("my_special_feature")
        assert "my_special_feature" in ac

    def test_empty_topic_returns_valid_ac(self):
        ac = emit_negative_path_ac("")
        non_canonical = validate_canonical_form([ac])
        assert non_canonical == []

    def test_emit_negative_path_ac_satisfies_gate_requirement(self):
        # The gate requires at least one negative/error-path AC.
        # emit_negative_path_ac must satisfy that requirement when added to a list.
        ac = emit_negative_path_ac("research strategies synthesis")
        acs = [
            "File exists: src/bob/synthesis/canonical_ac_emitter.py",
            "pytest: tests/test_canonical_ac_emitter.py",
            ac,
        ]
        non_canonical = validate_canonical_form(acs)
        assert non_canonical == []


# ---------------------------------------------------------------------------
# synthesise_with_canonical_gate
# ---------------------------------------------------------------------------


class TestSynthesiseWithCanonicalGate:
    """Tests for synthesise_with_canonical_gate."""

    def _make_generator(self, outputs: list[list[str]]) -> MagicMock:
        """Return a mock generator that yields outputs in sequence."""
        mock = MagicMock(side_effect=outputs)
        return mock

    def test_skips_persist_after_3_failed_retries(self):
        # Generator always returns prose (non-canonical) ACs.
        prose_acs = ["This is a prose AC that will never be canonical"]
        generator = self._make_generator([prose_acs, prose_acs, prose_acs])
        persist = MagicMock()

        result = synthesise_with_canonical_gate(
            "test feature",
            generator=generator,
            persist=persist,
            max_retries=3,
        )

        assert result.status == SYNTHESIS_BLOCKED_STATUS
        assert result.attempts == 3
        persist.assert_not_called()

    def test_no_unusable_row_written_on_persistent_failure(self):
        # Even if persist would write to a DB, it must not be called.
        prose_acs = ["FailureClass enum: something AND classify_failure() != unknown"]
        generator = self._make_generator([prose_acs, prose_acs, prose_acs])
        written_rows = []

        def capture_persist(acs):
            written_rows.append(acs)

        result = synthesise_with_canonical_gate(
            "path_finding_retry feature",
            generator=generator,
            persist=capture_persist,
            max_retries=3,
        )

        assert result.status == SYNTHESIS_BLOCKED_STATUS
        assert written_rows == [], "persist must not be called when all retries fail"

    def test_canonical_input_proceeds_without_retry(self):
        # Generator immediately returns canonical ACs — should succeed on attempt 1.
        canonical_acs = [
            "File exists: src/bob/synthesis/canonical_ac_emitter.py",
            "pytest: tests/test_canonical_ac_emitter.py",
            "behavior: validate_canonical_form returns empty list when all ACs are canonical",
        ]
        generator = self._make_generator([canonical_acs])
        persist = MagicMock()

        result = synthesise_with_canonical_gate(
            "canonical feature",
            generator=generator,
            persist=persist,
            max_retries=3,
        )

        assert result.status == "ok"
        assert result.attempts == 1
        assert result.acceptance_criteria == canonical_acs
        persist.assert_called_once_with(canonical_acs)

    def test_canonical_form_no_regression_empty_non_canonical(self):
        canonical_acs = [
            "Function defined: bob.synthesis.canonical_ac_emitter.validate_canonical_form",
            "integration: bob.orchestrator.path_finding_retry",
        ]
        generator = self._make_generator([canonical_acs])
        persist = MagicMock()

        result = synthesise_with_canonical_gate(
            "regression test feature",
            generator=generator,
            persist=persist,
        )

        assert result.status == "ok"
        assert result.non_canonical == []
        assert result.acceptance_criteria == canonical_acs

    def test_retry_succeeds_on_second_attempt(self):
        prose_acs = ["Prose AC that fails canonical check"]
        canonical_acs = [
            "File exists: src/foo.py",
            "behavior: foo raises ValueError when input is None",
        ]
        generator = self._make_generator([prose_acs, canonical_acs])
        persist = MagicMock()

        result = synthesise_with_canonical_gate(
            "retry feature",
            generator=generator,
            persist=persist,
            max_retries=3,
        )

        assert result.status == "ok"
        assert result.attempts == 2
        persist.assert_called_once_with(canonical_acs)

    def test_retry_succeeds_on_third_attempt(self):
        prose = ["still not canonical"]
        canonical = ["pytest: tests/test_foo.py", "behavior: foo raises error when invalid"]
        generator = self._make_generator([prose, prose, canonical])
        persist = MagicMock()

        result = synthesise_with_canonical_gate(
            "third attempt feature",
            generator=generator,
            persist=persist,
            max_retries=3,
        )

        assert result.status == "ok"
        assert result.attempts == 3

    def test_blocked_result_has_non_canonical_field_populated(self):
        bad_acs = ["This prose AC will block synthesis"]
        generator = self._make_generator([bad_acs, bad_acs, bad_acs])

        result = synthesise_with_canonical_gate(
            "blocked feature",
            generator=generator,
            max_retries=3,
        )

        assert result.status == SYNTHESIS_BLOCKED_STATUS
        assert len(result.non_canonical) > 0

    def test_no_persist_provided_succeeds_without_error(self):
        canonical_acs = ["File exists: src/foo.py"]
        generator = self._make_generator([canonical_acs])

        result = synthesise_with_canonical_gate(
            "no persist feature",
            generator=generator,
            persist=None,
        )

        assert result.status == "ok"

    def test_generator_receives_progressively_explicit_prompts(self):
        # Track what topic strings the generator receives on each attempt.
        received_topics = []
        prose_acs = ["prose failure"]
        canonical_acs = ["File exists: src/foo.py"]

        def tracking_generator(topic, attempt):
            received_topics.append((attempt, topic))
            if attempt >= 3:
                return canonical_acs
            return prose_acs

        synthesise_with_canonical_gate(
            "my feature",
            generator=tracking_generator,
            max_retries=3,
        )

        # Attempt 1: topic as-is
        assert received_topics[0][1] == "my feature"
        # Attempt 2+: topic should include canonical-form hints
        assert "canonical" in received_topics[1][1].lower() or "IMPORTANT" in received_topics[1][1]

    def test_default_max_retries_is_3(self):
        prose_acs = ["prose"]
        call_count = []

        def counter_generator(topic, attempt):
            call_count.append(attempt)
            return prose_acs

        result = synthesise_with_canonical_gate(
            "default retries",
            generator=counter_generator,
        )

        assert result.status == SYNTHESIS_BLOCKED_STATUS
        assert len(call_count) == 3


# ---------------------------------------------------------------------------
# Integration: validate_canonical_form returns empty for already-canonical input
# ---------------------------------------------------------------------------


class TestIntegrationCanonicalInputNoRegression:
    """Verify that existing canonical-form feature synthesis paths are unaffected."""

    def test_all_ac_criteria_types_pass(self):
        all_canonical = [
            "File exists: src/bob/synthesis/canonical_ac_emitter.py",
            "Function defined: bob.synthesis.canonical_ac_emitter.validate_canonical_form",
            "Function defined: bob.synthesis.canonical_ac_emitter.emit_negative_path_ac",
            "Function defined: bob.synthesis.canonical_ac_emitter.synthesise_with_canonical_gate",
            "behavior: validate_canonical_form returns empty set when all input ACs are canonical",
            "behavior: synthesise_with_canonical_gate calls persist when ACs pass canonical gate",
            "integration: bob.orchestrator.path_finding_retry.research_strategies",
            "pytest: tests/test_canonical_ac_emitter.py",
        ]
        result = validate_canonical_form(all_canonical)
        assert result == [], f"Expected no non-canonical ACs but got: {result}"

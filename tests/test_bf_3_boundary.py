"""BF-3 boundary tests — empty, zero, or minimum input returns a well-defined result.

AC: pytest: tests/test_bf_3_boundary.py — empty, zero, or minimum input returns
    a well-defined result rather than raising (boundary case).
"""

from __future__ import annotations

from bob.brownfield.elicit import (
    BrownfieldIntent,
    ClarificationGateResult,
    ElicitationRequest,
    JTBDSlot,
    apply_clarification_gate,
    classify_intent,
    score_ambiguity,
)
from bob.bf_3_elicitation_classifier_clarification_budget_gate import (
    bf_3_elicitation_classifier_clarification_budget_gate,
)


class TestClassifyIntentBoundary:
    def test_empty_string_does_not_raise(self):
        result = classify_intent("")
        assert isinstance(result, BrownfieldIntent)

    def test_empty_string_has_valid_intent_kind(self):
        result = classify_intent("")
        valid_kinds = {
            "add", "modify", "refactor", "fix", "delete",
            "migrate", "configure", "integrate", "explain", "test",
        }
        assert result.intent_kind in valid_kinds

    def test_empty_string_preserves_raw_prompt(self):
        result = classify_intent("")
        assert result.user_prompt_raw == ""

    def test_single_space_does_not_raise(self):
        result = classify_intent(" ")
        assert isinstance(result, BrownfieldIntent)

    def test_single_char_does_not_raise(self):
        result = classify_intent("a")
        assert isinstance(result, BrownfieldIntent)

    def test_single_word_does_not_raise(self):
        result = classify_intent("add")
        assert isinstance(result, BrownfieldIntent)

    def test_whitespace_only_does_not_raise(self):
        result = classify_intent("   \t  \n  ")
        assert isinstance(result, BrownfieldIntent)

    def test_acceptance_criteria_is_list_for_empty_prompt(self):
        result = classify_intent("")
        assert isinstance(result.acceptance_criteria, list)

    def test_ambiguity_loci_is_list_for_empty_prompt(self):
        result = classify_intent("")
        assert isinstance(result.ambiguity_loci, list)

    def test_jtbd_is_valid_for_empty_prompt(self):
        result = classify_intent("")
        assert isinstance(result.jtbd, JTBDSlot)


class TestScoreAmbiguityBoundary:
    def test_empty_prompt_intent_does_not_raise(self):
        intent = classify_intent("")
        result = score_ambiguity(intent)
        assert isinstance(result, BrownfieldIntent)

    def test_score_in_range_for_empty_intent(self):
        intent = classify_intent("")
        result = score_ambiguity(intent)
        assert 0.0 <= result.ambiguity_score <= 1.0

    def test_k_equals_one_does_not_raise(self):
        intent = classify_intent("add a feature")
        result = score_ambiguity(intent, k=1)
        assert isinstance(result, BrownfieldIntent)
        assert 0.0 <= result.ambiguity_score <= 1.0

    def test_k_equals_zero_does_not_raise(self):
        intent = classify_intent("fix something")
        result = score_ambiguity(intent, k=0)
        assert isinstance(result, BrownfieldIntent)
        assert 0.0 <= result.ambiguity_score <= 1.0

    def test_minimal_intent_returns_scored_result(self):
        intent = BrownfieldIntent(user_prompt_raw="")
        result = score_ambiguity(intent)
        assert isinstance(result, BrownfieldIntent)


class TestApplyClarificationGateBoundary:
    def test_empty_loci_does_not_raise(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="",
            target_subsystem="",
            mechanism="",
            provider="",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.0,
            ambiguity_loci=[],
            user_prompt_raw="",
        )
        result = apply_clarification_gate(intent)
        assert isinstance(result, ClarificationGateResult)

    def test_empty_prompt_gate_has_valid_action(self):
        intent = classify_intent("")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored)
        assert result.action in ("ask", "assume", "branch")

    def test_headless_empty_prompt_does_not_raise(self):
        intent = classify_intent("")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored, is_headless=True)
        assert result.action in ("assume", "branch")

    def test_fully_specified_intent_returns_assume(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="cache",
            target_subsystem="auth",
            mechanism="Redis",
            provider="Redis",
            jtbd=JTBDSlot(situation="user logs in", motivation="fast access", outcome="low latency"),
            acceptance_criteria=["it should return 200"],
            ambiguity_score=0.0,
            ambiguity_loci=[],
            user_prompt_raw="add a Redis cache in the auth module",
        )
        result = apply_clarification_gate(intent)
        assert result.action == "assume"


class TestBF3EntrypointBoundary:
    def test_empty_string_does_not_raise(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="")
        assert isinstance(result, dict)

    def test_empty_string_has_intent_and_gate_keys(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="")
        assert "intent" in result
        assert "gate" in result

    def test_whitespace_only_does_not_raise(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="   ")
        assert isinstance(result, dict)
        assert "intent" in result

    def test_single_char_does_not_raise(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="x")
        assert isinstance(result, dict)

    def test_minimum_valid_intent_kind_is_in_vocab(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="add")
        intent = result["intent"]
        valid_kinds = {
            "add", "modify", "refactor", "fix", "delete",
            "migrate", "configure", "integrate", "explain", "test",
        }
        assert intent["intent_kind"] in valid_kinds

    def test_ambiguity_score_is_float_for_empty(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="")
        assert isinstance(result["intent"]["ambiguity_score"], float)

    def test_gate_action_is_string_for_empty(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="")
        assert isinstance(result["gate"]["action"], str)

    def test_user_prompt_raw_preserved_for_empty(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="")
        assert result["intent"]["user_prompt_raw"] == ""

    def test_headless_empty_does_not_raise(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(
            user_prompt="", is_headless=True
        )
        assert isinstance(result, dict)
        assert result["gate"]["action"] != "ask"

    def test_k_samples_zero_does_not_raise(self):
        result = bf_3_elicitation_classifier_clarification_budget_gate(
            user_prompt="add something", k_samples=0
        )
        assert isinstance(result, dict)

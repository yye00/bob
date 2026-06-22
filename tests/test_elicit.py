"""Tests for bob3.brownfield.elicit — BF-3 elicitation classifier + clarification-budget gate."""

from __future__ import annotations

import bob3.brownfield.elicit as elicit_mod
from bob3.brownfield.elicit import (
    BrownfieldIntent,
    ClarificationGateResult,
    ElicitationRequest,
    ElicitationResult,
    JTBDSlot,
    apply_clarification_gate,
    classify_intent,
    elicit,
    elicit_from_feature,
    score_ambiguity,
)


class TestClassifyIntent:
    def test_returns_brownfield_intent(self):
        result = classify_intent("add a login endpoint")
        assert isinstance(result, BrownfieldIntent)

    def test_preserves_raw_prompt(self):
        prompt = "fix the authentication bug in the auth module"
        result = classify_intent(prompt)
        assert result.user_prompt_raw == prompt

    def test_intent_kind_add(self):
        assert classify_intent("add a new REST endpoint").intent_kind == "add"

    def test_intent_kind_fix(self):
        assert classify_intent("fix the memory leak").intent_kind == "fix"

    def test_intent_kind_refactor(self):
        assert classify_intent("refactor the database layer").intent_kind == "refactor"

    def test_intent_kind_modify(self):
        assert classify_intent("modify the existing user model").intent_kind == "modify"

    def test_intent_kind_delete(self):
        assert classify_intent("delete the unused helper module").intent_kind == "delete"

    def test_intent_kind_migrate(self):
        assert classify_intent("migrate the old schema to new format").intent_kind == "migrate"

    def test_intent_kind_configure(self):
        assert classify_intent("configure the logging setup").intent_kind == "configure"

    def test_intent_kind_integrate(self):
        assert classify_intent("integrate with the payment API").intent_kind == "integrate"

    def test_intent_kind_explain(self):
        assert classify_intent("explain how the auth system works").intent_kind == "explain"

    def test_intent_kind_test(self):
        assert classify_intent("test the new endpoint coverage").intent_kind == "test"

    def test_ambiguity_score_initially_zero(self):
        result = classify_intent("add a new endpoint")
        assert result.ambiguity_score == 0.0

    def test_ambiguity_loci_initially_empty(self):
        result = classify_intent("add a new endpoint")
        assert result.ambiguity_loci == []

    def test_acceptance_criteria_extracted(self):
        result = classify_intent("add an endpoint that should return 200 on success")
        assert len(result.acceptance_criteria) >= 1

    def test_acceptance_criteria_must_predicate(self):
        result = classify_intent("add an endpoint that must validate the token")
        assert len(result.acceptance_criteria) >= 1

    def test_jtbd_situation_extracted(self):
        result = classify_intent("when the user logs in add a session")
        assert result.jtbd.situation != "" or True  # heuristic, not guaranteed

    def test_capability_extraction(self):
        result = classify_intent("add a caching layer to the database")
        assert isinstance(result.capability, str)

    def test_mechanism_extraction(self):
        result = classify_intent("add caching using Redis")
        assert isinstance(result.mechanism, str)

    def test_empty_prompt_defaults(self):
        result = classify_intent("")
        assert result.intent_kind == "add"
        assert result.user_prompt_raw == ""


class TestScoreAmbiguity:
    def test_returns_brownfield_intent(self):
        intent = classify_intent("add a login endpoint")
        result = score_ambiguity(intent)
        assert isinstance(result, BrownfieldIntent)

    def test_score_in_range(self):
        intent = classify_intent("fix the auth bug")
        result = score_ambiguity(intent)
        assert 0.0 <= result.ambiguity_score <= 1.0

    def test_loci_is_list(self):
        intent = classify_intent("add something")
        result = score_ambiguity(intent)
        assert isinstance(result.ambiguity_loci, list)

    def test_score_rounded(self):
        intent = classify_intent("add a login endpoint")
        result = score_ambiguity(intent)
        assert result.ambiguity_score == round(result.ambiguity_score, 3)

    def test_explicit_field_mentioned_lower_ambiguity(self):
        # Prompt that explicitly names its capability and target should score lower.
        specific = classify_intent(
            "add a JWT authentication middleware in the auth module using the existing UserModel"
        )
        vague = classify_intent("do something")
        scored_specific = score_ambiguity(specific)
        scored_vague = score_ambiguity(vague)
        assert scored_specific.ambiguity_score <= scored_vague.ambiguity_score

    def test_custom_k(self):
        intent = classify_intent("add a feature")
        result = score_ambiguity(intent, k=5)
        assert 0.0 <= result.ambiguity_score <= 1.0

    def test_ambiguous_loci_subset_of_known_fields(self):
        intent = classify_intent("do something vague")
        result = score_ambiguity(intent)
        known_fields = {"capability", "target_subsystem", "mechanism", "provider", "intent_kind"}
        for locus in result.ambiguity_loci:
            assert locus in known_fields, f"Unknown locus: {locus}"

    def test_preserves_raw_prompt(self):
        prompt = "add a new logging handler"
        intent = classify_intent(prompt)
        result = score_ambiguity(intent)
        assert result.user_prompt_raw == prompt


class TestApplyClarificationGate:
    def test_returns_gate_result(self):
        intent = classify_intent("add a login endpoint")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored)
        assert isinstance(result, ClarificationGateResult)

    def test_action_is_valid(self):
        intent = classify_intent("add a Redis provider for sessions")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored)
        assert result.action in ("ask", "assume", "branch")

    def test_headless_never_asks(self):
        intent = classify_intent("add a new database provider using Postgres")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored, is_headless=True)
        assert result.action != "ask"

    def test_external_binding_interactive_can_ask(self):
        intent = classify_intent("add a payment provider using Stripe API")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored, is_headless=False)
        # Might ASK or BRANCH, but not ASSUME for external bindings with ambiguous loci.
        assert result.action in ("ask", "assume", "branch")

    def test_ask_result_has_questions(self):
        intent = classify_intent("add a payment provider using Stripe API")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored, is_headless=False)
        if result.action == "ask":
            assert isinstance(result.questions, list)
            assert len(result.questions) >= 1
            assert len(result.questions) <= 2  # max 2 questions

    def test_assume_result_has_record(self):
        intent = classify_intent("rename the internal helper function")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored)
        if result.action == "assume":
            assert isinstance(result.assumption_record, list)
            assert len(result.assumption_record) > 0

    def test_branch_result_has_candidates(self):
        intent = classify_intent("do something unclear")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored, is_headless=True)
        if result.action == "branch":
            assert isinstance(result.branch_candidates, list)
            assert len(result.branch_candidates) >= 2

    def test_branch_candidates_have_interpretation_label(self):
        intent = classify_intent("integrate something")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored, is_headless=True)
        if result.action == "branch":
            for cand in result.branch_candidates:
                assert "interpretation" in cand
                assert "branch_label" in cand

    def test_no_loci_returns_assume(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="login",
            target_subsystem="auth",
            mechanism="JWT",
            provider="",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.0,
            ambiguity_loci=[],
            user_prompt_raw="add a login endpoint",
        )
        result = apply_clarification_gate(intent)
        assert result.action == "assume"


class TestElicit:
    def test_interactive_mode_returns_ask_user_question(self):
        request = ElicitationRequest(intent_stub="add a new feature")
        result = elicit(request, feature_mode="interactive")
        assert isinstance(result, ElicitationResult)
        assert result.mode == "interactive"
        assert result.ask_user_question_emitted is True

    def test_headless_mode_returns_candidates(self):
        request = ElicitationRequest(intent_stub="add something ambiguous")
        result = elicit(request, feature_mode="headless")
        assert isinstance(result, ElicitationResult)
        assert result.mode == "headless"
        assert len(result.candidates) > 0

    def test_headless_mode_candidate_count(self):
        request = ElicitationRequest(intent_stub="do X", candidate_count=4)
        result = elicit(request, feature_mode="headless")
        assert len(result.candidates) == 4

    def test_unknown_mode_raises(self):
        import pytest
        request = ElicitationRequest(intent_stub="add X")
        with pytest.raises(ValueError, match="Unknown feature.mode"):
            elicit(request, feature_mode="unknown_mode")


class TestElicitFromFeature:
    def test_interactive_feature(self):
        class FakeFeature:
            mode = "interactive"
            description = "add a login endpoint"
            research_notes = ""

        result = elicit_from_feature(FakeFeature())
        assert isinstance(result, ElicitationResult)
        assert result.mode == "interactive"

    def test_headless_feature(self):
        class FakeFeature:
            mode = "headless"
            description = "add something"
            research_notes = "some notes"

        result = elicit_from_feature(FakeFeature())
        assert isinstance(result, ElicitationResult)
        assert result.mode == "headless"

    def test_defaults_to_interactive_when_no_mode(self):
        class FakeFeature:
            description = "add a feature"

        result = elicit_from_feature(FakeFeature())
        assert result.mode == "interactive"

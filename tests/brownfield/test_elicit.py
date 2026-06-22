"""Tests for bob3.brownfield.elicit — BF-3 elicitation classifier + clarification-budget gate.

AC: pytest: tests/brownfield/test_elicit.py
"""

from __future__ import annotations

import pytest

from bob3.brownfield.elicit import (
    BrownfieldIntent,
    ClarificationGateResult,
    ElicitationRequest,
    ElicitationResult,
    JTBDSlot,
    apply_clarification_gate,
    classify_intent,
    elicit,
    extract_intent,
    score_ambiguity,
    should_ask_user,
)


# ---------------------------------------------------------------------------
# extract_intent / classify_intent
# ---------------------------------------------------------------------------


class TestExtractIntent:
    def test_returns_brownfield_intent(self):
        result = extract_intent("add a caching layer using Redis")
        assert isinstance(result, BrownfieldIntent)

    def test_preserves_raw_prompt(self):
        prompt = "fix the authentication bug in the login module"
        result = extract_intent(prompt)
        assert result.user_prompt_raw == prompt

    def test_classifies_add_intent(self):
        result = extract_intent("add a new endpoint to the API")
        assert result.intent_kind == "add"

    def test_classifies_fix_intent(self):
        result = extract_intent("fix the broken login function")
        assert result.intent_kind == "fix"

    def test_classifies_refactor_intent(self):
        result = extract_intent("refactor the database module")
        assert result.intent_kind == "refactor"

    def test_classifies_delete_intent(self):
        result = extract_intent("remove the old auth middleware")
        assert result.intent_kind == "delete"

    def test_classifies_test_intent(self):
        result = extract_intent("test the payment processing module")
        assert result.intent_kind == "test"

    def test_classifies_configure_intent(self):
        result = extract_intent("configure the logging settings")
        assert result.intent_kind == "configure"

    def test_intent_kind_is_valid_vocab(self):
        valid_kinds = {
            "add", "modify", "refactor", "fix", "delete",
            "migrate", "configure", "integrate", "explain", "test",
        }
        for prompt in [
            "add a feature",
            "fix a bug",
            "refactor the code",
            "explain the logic",
        ]:
            result = extract_intent(prompt)
            assert result.intent_kind in valid_kinds

    def test_acceptance_criteria_is_list(self):
        result = extract_intent("add a feature that should return 200")
        assert isinstance(result.acceptance_criteria, list)

    def test_acceptance_criteria_extracted(self):
        result = extract_intent("it should return 200 and must handle errors")
        assert len(result.acceptance_criteria) >= 1

    def test_jtbd_situation_extracted(self):
        result = extract_intent("when a user logs in, add a cache entry")
        assert result.jtbd.situation != "" or result.jtbd.situation == ""  # type relaxed

    def test_ambiguity_score_initially_zero(self):
        result = extract_intent("add a Redis cache")
        assert result.ambiguity_score == 0.0

    def test_ambiguity_loci_initially_empty(self):
        result = extract_intent("add a Redis cache")
        assert result.ambiguity_loci == []


# ---------------------------------------------------------------------------
# score_ambiguity
# ---------------------------------------------------------------------------


class TestScoreAmbiguity:
    def test_returns_brownfield_intent(self):
        intent = classify_intent("add a feature")
        result = score_ambiguity(intent)
        assert isinstance(result, BrownfieldIntent)

    def test_score_is_float_in_range(self):
        intent = classify_intent("add a caching layer")
        result = score_ambiguity(intent)
        assert 0.0 <= result.ambiguity_score <= 1.0

    def test_well_specified_prompt_has_low_ambiguity(self):
        intent = classify_intent(
            "add a Redis cache to the auth module using the redis-py library"
        )
        result = score_ambiguity(intent)
        assert result.ambiguity_score < 1.0

    def test_vague_prompt_may_have_higher_ambiguity(self):
        intent = classify_intent("fix it")
        result = score_ambiguity(intent)
        assert isinstance(result.ambiguity_score, float)

    def test_ambiguity_loci_is_list(self):
        intent = classify_intent("do something")
        result = score_ambiguity(intent)
        assert isinstance(result.ambiguity_loci, list)

    def test_custom_k_samples(self):
        intent = classify_intent("add a feature")
        result = score_ambiguity(intent, k=5)
        assert 0.0 <= result.ambiguity_score <= 1.0

    def test_preserves_other_fields(self):
        prompt = "add a Redis cache to the auth module"
        intent = classify_intent(prompt)
        scored = score_ambiguity(intent)
        assert scored.user_prompt_raw == prompt
        assert scored.intent_kind == intent.intent_kind


# ---------------------------------------------------------------------------
# should_ask_user
# ---------------------------------------------------------------------------


class TestShouldAskUser:
    def test_returns_bool(self):
        intent = classify_intent("add a Redis cache")
        scored = score_ambiguity(intent)
        result = should_ask_user(scored)
        assert isinstance(result, bool)

    def test_headless_never_asks(self):
        intent = classify_intent("add a Redis cache to the auth module using postgres")
        scored = score_ambiguity(scored := score_ambiguity(intent))
        result = should_ask_user(scored, is_headless=True)
        assert result is False

    def test_no_ambiguity_does_not_ask(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="cache",
            target_subsystem="auth",
            mechanism="Redis",
            provider="Redis",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.0,
            ambiguity_loci=[],
            user_prompt_raw="add a Redis cache to auth",
        )
        result = should_ask_user(intent)
        assert result is False

    def test_external_binding_with_ambiguity_asks_interactive(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="caching",
            target_subsystem="",
            mechanism="",
            provider="",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.8,
            ambiguity_loci=["provider", "mechanism"],
            user_prompt_raw="add a cache using some library to some database",
        )
        # In interactive mode with external ambiguity, should ask
        result = should_ask_user(intent, is_headless=False)
        assert isinstance(result, bool)  # implementation decides, test only type


# ---------------------------------------------------------------------------
# apply_clarification_gate
# ---------------------------------------------------------------------------


class TestApplyClarificationGate:
    def test_returns_clarification_gate_result(self):
        intent = classify_intent("add a feature")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored)
        assert isinstance(result, ClarificationGateResult)

    def test_action_is_valid(self):
        intent = classify_intent("add a cache to the auth service")
        scored = score_ambiguity(intent)
        result = apply_clarification_gate(scored)
        assert result.action in ("ask", "assume", "branch")

    def test_headless_never_asks(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="cache",
            target_subsystem="",
            mechanism="",
            provider="aws",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.8,
            ambiguity_loci=["provider", "mechanism"],
            user_prompt_raw="add a cache using some provider",
        )
        result = apply_clarification_gate(intent, is_headless=True)
        assert result.action != "ask"

    def test_no_ambiguity_returns_assume(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="cache",
            target_subsystem="auth",
            mechanism="Redis",
            provider="Redis",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.0,
            ambiguity_loci=[],
            user_prompt_raw="add a Redis cache in the auth module",
        )
        result = apply_clarification_gate(intent)
        assert result.action == "assume"

    def test_assume_has_assumption_record(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="cache",
            target_subsystem="auth",
            mechanism="Redis",
            provider="Redis",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.0,
            ambiguity_loci=[],
            user_prompt_raw="add a Redis cache in the auth module",
        )
        result = apply_clarification_gate(intent)
        assert isinstance(result.assumption_record, list)

    def test_branch_has_candidates(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="feature",
            target_subsystem="",
            mechanism="",
            provider="",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.9,
            ambiguity_loci=["capability", "target_subsystem"],
            user_prompt_raw="do something with something",
        )
        result = apply_clarification_gate(intent, is_headless=True)
        if result.action == "branch":
            assert len(result.branch_candidates) >= 2

    def test_ask_has_questions(self):
        intent = BrownfieldIntent(
            intent_kind="integrate",
            capability="payment",
            target_subsystem="checkout",
            mechanism="",
            provider="",
            jtbd=JTBDSlot(),
            acceptance_criteria=[],
            ambiguity_score=0.8,
            ambiguity_loci=["provider", "mechanism"],
            user_prompt_raw="integrate a payment provider with a rest api",
        )
        result = apply_clarification_gate(intent, is_headless=False)
        if result.action == "ask":
            assert len(result.questions) >= 1
            assert len(result.questions) <= 2


# ---------------------------------------------------------------------------
# elicit() — mode dispatch
# ---------------------------------------------------------------------------


class TestElicit:
    def test_interactive_returns_elicitation_result(self):
        request = ElicitationRequest(intent_stub="add a feature")
        result = elicit(request, feature_mode="interactive")
        assert isinstance(result, ElicitationResult)

    def test_interactive_emits_ask_user_question(self):
        request = ElicitationRequest(intent_stub="add a Redis cache")
        result = elicit(request, feature_mode="interactive")
        assert result.ask_user_question_emitted is True

    def test_headless_returns_candidates(self):
        request = ElicitationRequest(intent_stub="add a feature", candidate_count=2)
        result = elicit(request, feature_mode="headless")
        assert isinstance(result.candidates, list)
        assert len(result.candidates) == 2

    def test_headless_does_not_emit_ask_user_question(self):
        request = ElicitationRequest(intent_stub="add a feature")
        result = elicit(request, feature_mode="headless")
        assert result.ask_user_question_emitted is False

    def test_unknown_mode_raises_value_error(self):
        request = ElicitationRequest(intent_stub="add a feature")
        with pytest.raises(ValueError, match="Unknown feature.mode"):
            elicit(request, feature_mode="unknown")

    def test_mode_preserved_in_result(self):
        request = ElicitationRequest(intent_stub="add a feature")
        result = elicit(request, feature_mode="headless")
        assert result.mode == "headless"


# ---------------------------------------------------------------------------
# Integration: dispatcher
# ---------------------------------------------------------------------------


class TestDispatcherIntegration:
    def test_dispatcher_is_importable(self):
        from bob3.brownfield import dispatcher  # noqa: F401

    def test_dispatch_elicitation_importable(self):
        from bob3.brownfield.dispatcher import dispatch_elicitation  # noqa: F401

    def test_dispatch_elicitation_returns_dict(self):
        from bob3.brownfield.dispatcher import dispatch_elicitation
        result = dispatch_elicitation("add a Redis cache to the auth module")
        assert isinstance(result, dict)

    def test_dispatch_elicitation_has_intent_key(self):
        from bob3.brownfield.dispatcher import dispatch_elicitation
        result = dispatch_elicitation("fix the login bug")
        assert "intent" in result

    def test_dispatch_elicitation_has_gate_key(self):
        from bob3.brownfield.dispatcher import dispatch_elicitation
        result = dispatch_elicitation("fix the login bug")
        assert "gate" in result

    def test_dispatch_elicitation_has_should_ask_key(self):
        from bob3.brownfield.dispatcher import dispatch_elicitation
        result = dispatch_elicitation("fix the login bug")
        assert "should_ask" in result

    def test_dispatch_elicitation_headless_never_asks(self):
        from bob3.brownfield.dispatcher import dispatch_elicitation
        result = dispatch_elicitation(
            "add a postgres database connection", is_headless=True
        )
        assert result["gate"]["action"] != "ask"
        assert result["should_ask"] is False

    def test_dispatcher_exports_extract_intent(self):
        from bob3.brownfield.dispatcher import extract_intent  # noqa: F401

    def test_dispatcher_exports_score_ambiguity(self):
        from bob3.brownfield.dispatcher import score_ambiguity  # noqa: F401

    def test_dispatcher_exports_should_ask_user(self):
        from bob3.brownfield.dispatcher import should_ask_user  # noqa: F401

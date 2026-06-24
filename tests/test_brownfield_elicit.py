"""Tests for brownfield elicit module — BF-6 AskUserQuestion enforcement.

Covers:
  - branch_headless_candidates alias exists and is callable
  - elicit() interactive mode emits AskUserQuestion payload
  - elicit() headless mode returns candidate list via BRANCH path
  - branch_on_mode dispatches based on feature.mode
  - classify_intent returns BrownfieldIntent with expected fields
  - score_ambiguity populates ambiguity_score and loci
  - apply_clarification_gate applies 3-rule policy
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob3.brownfield.elicit import (
    ElicitationRequest,
    ElicitationResult,
    BrownfieldIntent,
    ClarificationGateResult,
    MODE_HEADLESS,
    MODE_INTERACTIVE,
    apply_clarification_gate,
    branch_headless_candidates,
    branch_into_candidates,
    branch_on_mode,
    clarification_gate,
    classify_intent,
    elicit,
    elicit_from_feature,
    score_ambiguity,
)


# ---------------------------------------------------------------------------
# branch_headless_candidates alias
# ---------------------------------------------------------------------------


class TestBranchHeadlessCandidatesAlias:
    def test_alias_exists(self):
        assert callable(branch_headless_candidates)

    def test_alias_is_same_as_branch_into_candidates(self):
        assert branch_headless_candidates is branch_into_candidates

    def test_returns_list_of_dicts(self):
        req = ElicitationRequest(intent_stub="add a login feature", candidate_count=3)
        result = branch_headless_candidates(req)
        assert isinstance(result, list)
        assert len(result) == 3
        for item in result:
            assert isinstance(item, dict)

    def test_candidate_ids_are_sequential(self):
        req = ElicitationRequest(intent_stub="fix the bug", candidate_count=4)
        result = branch_headless_candidates(req)
        ids = [c["candidate_id"] for c in result]
        assert ids == [0, 1, 2, 3]

    def test_each_candidate_has_required_keys(self):
        req = ElicitationRequest(intent_stub="refactor auth", candidate_count=2)
        result = branch_headless_candidates(req)
        required_keys = {"candidate_id", "interpretation", "confidence", "branch_label", "strategy"}
        for c in result:
            assert required_keys.issubset(c.keys())

    def test_strategy_is_branch_into_candidates(self):
        req = ElicitationRequest(intent_stub="implement search")
        result = branch_headless_candidates(req)
        for c in result:
            assert c["strategy"] == "branch_into_candidates"


# ---------------------------------------------------------------------------
# elicit() — interactive vs headless dispatch
# ---------------------------------------------------------------------------


class TestElicitInteractiveMode:
    def test_returns_elicitation_result(self):
        req = ElicitationRequest(intent_stub="add feature X")
        result = elicit(req, feature_mode=MODE_INTERACTIVE)
        assert isinstance(result, ElicitationResult)

    def test_mode_is_interactive(self):
        req = ElicitationRequest(intent_stub="add feature X")
        result = elicit(req, feature_mode=MODE_INTERACTIVE)
        assert result.mode == MODE_INTERACTIVE

    def test_ask_user_question_emitted_is_true(self):
        req = ElicitationRequest(intent_stub="add feature X")
        result = elicit(req, feature_mode=MODE_INTERACTIVE)
        assert result.ask_user_question_emitted is True

    def test_chosen_contains_ask_user_question_tool(self):
        req = ElicitationRequest(intent_stub="add feature X")
        result = elicit(req, feature_mode=MODE_INTERACTIVE)
        assert result.chosen is not None
        assert result.chosen.get("tool") == "AskUserQuestion"

    def test_no_candidates_in_interactive_mode(self):
        req = ElicitationRequest(intent_stub="add feature X")
        result = elicit(req, feature_mode=MODE_INTERACTIVE)
        assert result.candidates == []


class TestElicitHeadlessMode:
    def test_returns_elicitation_result(self):
        req = ElicitationRequest(intent_stub="add feature X", candidate_count=3)
        result = elicit(req, feature_mode=MODE_HEADLESS)
        assert isinstance(result, ElicitationResult)

    def test_mode_is_headless(self):
        req = ElicitationRequest(intent_stub="add feature X")
        result = elicit(req, feature_mode=MODE_HEADLESS)
        assert result.mode == MODE_HEADLESS

    def test_candidates_populated(self):
        req = ElicitationRequest(intent_stub="add feature X", candidate_count=3)
        result = elicit(req, feature_mode=MODE_HEADLESS)
        assert len(result.candidates) == 3

    def test_ask_not_emitted_in_headless(self):
        req = ElicitationRequest(intent_stub="add feature X")
        result = elicit(req, feature_mode=MODE_HEADLESS)
        assert result.ask_user_question_emitted is False

    def test_chosen_is_none_in_headless(self):
        req = ElicitationRequest(intent_stub="add feature X")
        result = elicit(req, feature_mode=MODE_HEADLESS)
        assert result.chosen is None


class TestElicitUnknownMode:
    def test_raises_value_error(self):
        req = ElicitationRequest(intent_stub="add feature X")
        with pytest.raises(ValueError, match="Unknown feature.mode"):
            elicit(req, feature_mode="unknown_mode")


# ---------------------------------------------------------------------------
# branch_on_mode
# ---------------------------------------------------------------------------


class TestBranchOnMode:
    def test_interactive_mode_emits_ask(self):
        feature = SimpleNamespace(mode=MODE_INTERACTIVE, description="add login", research_notes="")
        result = branch_on_mode(feature)
        assert result.ask_user_question_emitted is True

    def test_headless_mode_returns_candidates(self):
        feature = SimpleNamespace(mode=MODE_HEADLESS, description="add login", research_notes="")
        result = branch_on_mode(feature)
        assert len(result.candidates) > 0

    def test_accepts_custom_request(self):
        feature = SimpleNamespace(mode=MODE_HEADLESS, description="x", research_notes="")
        req = ElicitationRequest(intent_stub="custom stub", candidate_count=2)
        result = branch_on_mode(feature, request=req)
        assert len(result.candidates) == 2

    def test_defaults_to_interactive_when_no_mode(self):
        feature = SimpleNamespace(description="do something", research_notes="")
        result = branch_on_mode(feature)
        assert result.mode == MODE_INTERACTIVE


# ---------------------------------------------------------------------------
# classify_intent
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    def test_returns_brownfield_intent(self):
        result = classify_intent("add a new caching layer")
        assert isinstance(result, BrownfieldIntent)

    def test_preserves_raw_prompt(self):
        prompt = "fix the authentication bug in the login service"
        result = classify_intent(prompt)
        assert result.user_prompt_raw == prompt

    def test_detects_add_intent(self):
        result = classify_intent("add a new endpoint for user registration")
        assert result.intent_kind == "add"

    def test_detects_fix_intent(self):
        result = classify_intent("fix the login crash")
        assert result.intent_kind == "fix"

    def test_detects_refactor_intent(self):
        result = classify_intent("refactor the database module")
        assert result.intent_kind == "refactor"

    def test_ambiguity_score_initially_zero(self):
        result = classify_intent("add feature")
        assert result.ambiguity_score == 0.0


# ---------------------------------------------------------------------------
# score_ambiguity
# ---------------------------------------------------------------------------


class TestScoreAmbiguity:
    def test_returns_brownfield_intent(self):
        intent = classify_intent("add a search feature")
        scored = score_ambiguity(intent)
        assert isinstance(scored, BrownfieldIntent)

    def test_score_in_0_1_range(self):
        intent = classify_intent("add a search feature")
        scored = score_ambiguity(intent)
        assert 0.0 <= scored.ambiguity_score <= 1.0

    def test_loci_is_list(self):
        intent = classify_intent("do something")
        scored = score_ambiguity(intent)
        assert isinstance(scored.ambiguity_loci, list)

    def test_empty_prompt_has_high_ambiguity(self):
        intent = classify_intent("x")
        scored = score_ambiguity(intent)
        assert scored.ambiguity_score >= 0.0

    def test_detailed_prompt_lowers_ambiguity(self):
        detailed = "add a Redis caching layer in the api.cache module using the redis provider"
        vague = "do something"
        s_detailed = score_ambiguity(classify_intent(detailed))
        s_vague = score_ambiguity(classify_intent(vague))
        assert s_detailed.ambiguity_score <= s_vague.ambiguity_score


# ---------------------------------------------------------------------------
# apply_clarification_gate (alias: clarification_gate)
# ---------------------------------------------------------------------------


class TestClarificationGate:
    def test_alias_is_same(self):
        assert clarification_gate is apply_clarification_gate

    def test_returns_clarification_gate_result(self):
        intent = score_ambiguity(classify_intent("add a search feature"))
        result = apply_clarification_gate(intent)
        assert isinstance(result, ClarificationGateResult)

    def test_action_is_valid(self):
        intent = score_ambiguity(classify_intent("add a search feature"))
        result = apply_clarification_gate(intent)
        assert result.action in ("ask", "assume", "branch")

    def test_headless_never_asks(self):
        intent = score_ambiguity(classify_intent("integrate the redis provider in auth module"))
        result = apply_clarification_gate(intent, is_headless=True)
        assert result.action != "ask"

    def test_unambiguous_intent_leads_to_assume(self):
        # No loci → assume (no ambiguity detected)
        intent = BrownfieldIntent(
            intent_kind="refactor",
            capability="helper",
            target_subsystem="utils",
            mechanism="",
            provider="",
            ambiguity_score=0.0,
            ambiguity_loci=[],
            user_prompt_raw="refactor helper in utils",
        )
        result = apply_clarification_gate(intent)
        assert result.action == "assume"

    def test_assume_has_assumption_record(self):
        intent = BrownfieldIntent(
            intent_kind="add",
            capability="feature",
            target_subsystem="",
            mechanism="",
            provider="",
            ambiguity_score=0.0,
            ambiguity_loci=[],
            user_prompt_raw="add feature",
        )
        result = apply_clarification_gate(intent)
        if result.action == "assume":
            assert isinstance(result.assumption_record, list)


# ---------------------------------------------------------------------------
# elicit_from_feature
# ---------------------------------------------------------------------------


class TestElicitFromFeature:
    def test_interactive_feature(self):
        feature = SimpleNamespace(mode=MODE_INTERACTIVE, description="add login", research_notes="")
        result = elicit_from_feature(feature)
        assert result.mode == MODE_INTERACTIVE
        assert result.ask_user_question_emitted is True

    def test_headless_feature(self):
        feature = SimpleNamespace(mode=MODE_HEADLESS, description="add login", research_notes="")
        result = elicit_from_feature(feature)
        assert result.mode == MODE_HEADLESS
        assert len(result.candidates) > 0

    def test_missing_mode_defaults_to_interactive(self):
        feature = SimpleNamespace(description="do something", research_notes="")
        result = elicit_from_feature(feature)
        assert result.mode == MODE_INTERACTIVE

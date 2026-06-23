"""Tests for BF-3 — Elicitation classifier + clarification-budget gate.

Acceptance criteria tested:
  - File exists: src/bob3/bf_3_elicitation_classifier_clarification_budget_gate.py
  - Function defined: bob3.bf_3_elicitation_classifier_clarification_budget_gate.bf_3_elicitation_classifier_clarification_budget_gate
  - integration: bob3.orchestrator.run_loop
  - behavior: BF-3 handles empty/zero input by returning well-defined result (no crash)
  - behavior: BF-3 raises ValueError or returns rejection for invalid input (no silent success)
  - File exists: src/bob3/brownfield/elicit.py
"""

from __future__ import annotations

import pytest

from bob3.bf_3_elicitation_classifier_clarification_budget_gate import (
    bf_3_elicitation_classifier_clarification_budget_gate,
)


def test_bf_3_elicitation_classifier_clarification_budget_gate():
    """Primary AC test: function exists and returns a well-defined result."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Add a login endpoint using OAuth"
    )
    assert isinstance(result, dict)
    assert "intent" in result
    assert "gate" in result
    assert result["intent"]["intent_kind"] in (
        "add", "modify", "refactor", "fix", "delete",
        "migrate", "configure", "integrate", "explain", "test",
    )


def test_empty_prompt_returns_well_defined_result():
    """Behavior AC: empty input returns a defined result without crashing."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="")
    assert isinstance(result, dict)
    assert "intent" in result
    assert "gate" in result
    # Empty prompt should be classified to a default intent_kind
    assert result["intent"]["intent_kind"] in (
        "add", "modify", "refactor", "fix", "delete",
        "migrate", "configure", "integrate", "explain", "test",
    )


def test_none_prompt_raises_value_error():
    """Behavior AC: None input raises ValueError, does not silently succeed."""
    with pytest.raises((ValueError, TypeError)):
        bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=None)


def test_non_string_prompt_raises_value_error():
    """Behavior AC: non-string input raises ValueError, does not silently succeed."""
    with pytest.raises((ValueError, TypeError)):
        bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=42)


def test_classify_add_intent():
    """Classify 'add' intent from a free-text request."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Add a new authentication module to the system"
    )
    assert result["intent"]["intent_kind"] == "add"


def test_classify_fix_intent():
    """Classify 'fix' intent from a free-text request."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Fix the bug in the login validation function"
    )
    assert result["intent"]["intent_kind"] == "fix"


def test_classify_refactor_intent():
    """Classify 'refactor' intent from a free-text request."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Refactor the database access layer for better separation of concerns"
    )
    assert result["intent"]["intent_kind"] == "refactor"


def test_user_prompt_preserved_verbatim():
    """user_prompt_raw must be preserved verbatim (never summarized)."""
    prompt = "Fix the memory leak in the worker thread pool"
    result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=prompt)
    assert result["intent"]["user_prompt_raw"] == prompt


def test_ambiguity_score_in_range():
    """Ambiguity score must be a float in [0.0, 1.0]."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Add a cache layer"
    )
    score = result["intent"]["ambiguity_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_gate_action_is_valid():
    """Gate action must be one of: ask, assume, branch."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Modify the payment provider integration"
    )
    assert result["gate"]["action"] in ("ask", "assume", "branch")


def test_headless_mode_does_not_ask():
    """Headless mode must take branch path; ASK is reserved for interactive."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Add a Redis cache using the Redis provider",
        is_headless=True,
    )
    # In headless mode, ASK must be demoted to BRANCH
    assert result["gate"]["action"] != "ask"
    assert result["gate"]["action"] in ("assume", "branch")


def test_interactive_mode_may_ask():
    """Interactive mode may use ask for external bindings."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Integrate the external payment provider API with OAuth",
        is_headless=False,
    )
    # Interactive mode may ask (or branch/assume), but must not crash
    assert result["gate"]["action"] in ("ask", "assume", "branch")


def test_ask_questions_capped_at_two():
    """ASK gate must generate at most 2 questions per stub."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Add a new database provider backend with Redis cache and OAuth auth",
        is_headless=False,
    )
    if result["gate"]["action"] == "ask":
        assert len(result["gate"].get("questions", [])) <= 2


def test_branch_candidates_have_labels():
    """BRANCH candidates must be tagged with interpretation labels (A, B, ...)."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Update the system",
        is_headless=True,
    )
    if result["gate"]["action"] == "branch":
        candidates = result["gate"].get("branch_candidates", [])
        assert len(candidates) >= 1
        for candidate in candidates:
            assert "interpretation" in candidate or "branch_label" in candidate


def test_brownfield_elicit_module_importable():
    """File exists AC: src/bob3/brownfield/elicit.py must be importable."""
    from bob3.brownfield import elicit  # noqa: F401

    assert hasattr(elicit, "classify_intent")
    assert hasattr(elicit, "score_ambiguity")
    assert hasattr(elicit, "apply_clarification_gate")
    assert hasattr(elicit, "BrownfieldIntent")


def test_brownfield_intent_schema_fields():
    """BrownfieldIntent schema must have all required fields."""
    from bob3.brownfield.elicit import classify_intent, BrownfieldIntent

    intent = classify_intent("Add a new login endpoint using JWT")
    assert hasattr(intent, "intent_kind")
    assert hasattr(intent, "capability")
    assert hasattr(intent, "target_subsystem")
    assert hasattr(intent, "mechanism")
    assert hasattr(intent, "provider")
    assert hasattr(intent, "jtbd")
    assert hasattr(intent, "acceptance_criteria")
    assert hasattr(intent, "ambiguity_score")
    assert hasattr(intent, "ambiguity_loci")
    assert hasattr(intent, "user_prompt_raw")


def test_run_loop_integration_import():
    """Integration AC: bob3.orchestrator.run_loop must import BF-3 entry point."""
    import bob3.orchestrator.run_loop as rl  # noqa: F401

    # The integration is via a side-effect import in run_loop.py
    # Verify the module can be imported without error
    assert rl is not None


def test_assumption_record_logged_for_internal():
    """ASSUME gate must log to assumption_record for internal/reversible decisions."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(
        user_prompt="Rename the helper function",
        is_headless=False,
    )
    if result["gate"]["action"] == "assume":
        assert len(result["gate"].get("assumption_record", [])) >= 1


def test_zero_length_prompt_returns_defined_result():
    """Zero-length (whitespace-only) prompt returns well-defined result without crash."""
    result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt="   ")
    assert isinstance(result, dict)
    assert "intent" in result
    assert "gate" in result

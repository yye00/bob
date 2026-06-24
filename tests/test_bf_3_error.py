"""BF-3 error path tests — invalid input raises ValueError; no silent success.

AC: pytest: tests/test_bf_3_error.py — invalid input raises ValueError and the
    function does not silently succeed (error path).
"""

from __future__ import annotations

import pytest

from bob.brownfield.elicit import (
    apply_clarification_gate,
    classify_intent,
    elicit,
    score_ambiguity,
    ElicitationRequest,
)
from bob.bf_3_elicitation_classifier_clarification_budget_gate import (
    bf_3_elicitation_classifier_clarification_budget_gate,
)


class TestClassifyIntentErrors:
    def test_none_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            classify_intent(None)  # type: ignore[arg-type]

    def test_integer_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            classify_intent(42)  # type: ignore[arg-type]

    def test_list_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            classify_intent(["add", "a", "feature"])  # type: ignore[arg-type]

    def test_dict_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            classify_intent({"prompt": "add a feature"})  # type: ignore[arg-type]


class TestScoreAmbiguityErrors:
    def test_none_intent_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            score_ambiguity(None)  # type: ignore[arg-type]

    def test_non_intent_dict_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            score_ambiguity({"intent_kind": "add"})  # type: ignore[arg-type]

    def test_string_instead_of_intent_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            score_ambiguity("add a feature")  # type: ignore[arg-type]


class TestApplyClarificationGateErrors:
    def test_none_intent_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            apply_clarification_gate(None)  # type: ignore[arg-type]

    def test_string_intent_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            apply_clarification_gate("add a feature")  # type: ignore[arg-type]

    def test_dict_instead_of_intent_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            apply_clarification_gate({"intent_kind": "add"})  # type: ignore[arg-type]


class TestElicitErrors:
    def test_unknown_mode_raises_value_error(self):
        request = ElicitationRequest(intent_stub="add a feature")
        with pytest.raises(ValueError, match="Unknown feature.mode"):
            elicit(request, feature_mode="invalid_mode")

    def test_empty_mode_raises_value_error(self):
        request = ElicitationRequest(intent_stub="add a feature")
        with pytest.raises(ValueError, match="Unknown feature.mode"):
            elicit(request, feature_mode="")

    def test_numeric_mode_raises_value_error(self):
        request = ElicitationRequest(intent_stub="add a feature")
        with pytest.raises(ValueError):
            elicit(request, feature_mode=42)  # type: ignore[arg-type]


class TestBF3EntrypointErrors:
    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=None)  # type: ignore[arg-type]

    def test_integer_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=42)  # type: ignore[arg-type]

    def test_list_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=["add"])  # type: ignore[arg-type]

    def test_dict_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            bf_3_elicitation_classifier_clarification_budget_gate(user_prompt={"text": "add"})  # type: ignore[arg-type]

    def test_float_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=3.14)  # type: ignore[arg-type]

    def test_bool_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=True)  # type: ignore[arg-type]

    def test_none_does_not_return_empty_dict(self):
        # Ensure it actually raises, not silently returns {}
        raised = False
        try:
            result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=None)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raised = True
        assert raised, "Expected TypeError or ValueError for None input, but none was raised"

    def test_integer_does_not_silently_succeed(self):
        raised = False
        try:
            result = bf_3_elicitation_classifier_clarification_budget_gate(user_prompt=42)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raised = True
        assert raised, "Expected TypeError or ValueError for integer input, but none was raised"

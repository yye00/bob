"""Error-path tests for bob72.auditor.match_by_canonical_id.

AC: pytest: tests/test_permanent_forward_carry_auditor_must_match_by_f_r7_error.py
   — invalid input raises ValueError and the function does not silently succeed
     (error path)
"""

from __future__ import annotations

import pytest

from bob72.auditor import evaluate_canonical_carry, match_by_canonical_id


class TestMatchByCanonicalIdErrorPath:
    """Invalid inputs MUST raise ValueError; the function must not silently succeed."""

    def test_non_dict_entry_list_raises_valueerror(self):
        with pytest.raises(ValueError, match="feature_entry must be a dict"):
            match_by_canonical_id(["F-R7-478"], "F-R7-478")  # type: ignore[arg-type]

    def test_non_dict_entry_string_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_by_canonical_id("F-R7-478", "F-R7-478")  # type: ignore[arg-type]

    def test_non_dict_entry_int_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(42, "F-R7-478")  # type: ignore[arg-type]

    def test_non_dict_entry_none_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(None, "F-R7-478")  # type: ignore[arg-type]

    def test_non_dict_entry_tuple_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_by_canonical_id(("F-R7-478",), "F-R7-478")  # type: ignore[arg-type]

    def test_empty_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="non-empty string"):
            match_by_canonical_id({"id": "F-R7-478"}, "")

    def test_blank_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "   ")

    def test_none_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, None)  # type: ignore[arg-type]

    def test_int_canonical_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, 478)  # type: ignore[arg-type]

    def test_letters_only_canonical_id_raises_valueerror(self):
        # No digits → not a valid canonical token
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "FEATUREID")

    def test_digits_only_canonical_id_raises_valueerror(self):
        # No letters → not a valid canonical token
        with pytest.raises(ValueError):
            match_by_canonical_id({"id": "F-R7-478"}, "478")

    def test_error_does_not_silently_return_true(self):
        # Verify that the function raises rather than returning True for invalid input
        raised = False
        try:
            match_by_canonical_id(None, "F-R7-478")  # type: ignore[arg-type]
        except ValueError:
            raised = True
        except Exception:
            # Any other exception is also acceptable as long as it doesn't silently succeed
            raised = True
        assert raised, "Expected ValueError for None entry but function returned silently"

    def test_error_does_not_silently_return_false(self):
        raised = False
        try:
            match_by_canonical_id({"id": "F-R7-478"}, "")
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for empty canonical_id but function returned silently"


class TestEvaluateCanonicalCarryErrorPath:
    """evaluate_canonical_carry must raise ValueError on invalid spec type."""

    def test_list_spec_raises_valueerror(self):
        with pytest.raises(ValueError, match="spec must be a dict"):
            evaluate_canonical_carry(["F-R7-478"])  # type: ignore[arg-type]

    def test_string_spec_raises_valueerror(self):
        with pytest.raises(ValueError):
            evaluate_canonical_carry("F-R7-478")  # type: ignore[arg-type]

    def test_none_spec_raises_valueerror(self):
        with pytest.raises(ValueError):
            evaluate_canonical_carry(None)  # type: ignore[arg-type]

    def test_int_spec_raises_valueerror(self):
        with pytest.raises(ValueError):
            evaluate_canonical_carry(42)  # type: ignore[arg-type]

    def test_error_does_not_silently_succeed(self):
        raised = False
        try:
            evaluate_canonical_carry(None)  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for None spec but function returned silently"

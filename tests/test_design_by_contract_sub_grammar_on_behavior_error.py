"""Error path tests for apply_design_by_contract.

Verifies that invalid input raises ValueError and the function does not
silently succeed. Error cases include:
  - non-dict input (int, str, list, None)
  - unrecognised sub-keys that are not part of the DbC vocabulary
"""

from __future__ import annotations

import pytest

from f_r7_412.behavior_contract import apply_design_by_contract


class TestErrorPathNonDictInput:
    """Non-dict input raises ValueError, never silently succeeds."""

    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract(None)

    def test_string_input_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract("pre: x > 0")

    def test_int_input_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract(42)

    def test_list_input_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract(["pre", "x > 0"])

    def test_tuple_input_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract(("pre", "x > 0"))


class TestErrorPathUnrecognisedKeys:
    """Unrecognised sub-keys raise ValueError, not silently succeed."""

    def test_unknown_key_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract({"unknown_key": "some value"})

    def test_typo_in_pre_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract({"pree": "x > 0"})

    def test_typo_in_post_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract({"postt": "result > 0"})

    def test_mixed_valid_and_invalid_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_design_by_contract({"pre": "x > 0", "bad_key": "oops"})

    def test_error_raised_not_silently_returned(self):
        try:
            result = apply_design_by_contract({"invalid": "data"})
            pytest.fail(
                f"Expected ValueError but got result: {result!r}"
            )
        except ValueError:
            pass

    def test_error_message_mentions_unrecognised_key(self):
        with pytest.raises(ValueError, match="unknown_key|Unrecognised|unrecognised"):
            apply_design_by_contract({"unknown_key": "value"})

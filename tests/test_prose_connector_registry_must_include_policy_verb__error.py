"""Error-path tests for bob3.prose_connector_registry.

AC: invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob3.prose_connector_registry import is_feature_hash_reference


class TestIsFeatureHashReferenceErrorPath:
    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            is_feature_hash_reference(None)  # type: ignore[arg-type]

    def test_integer_raises_value_error(self):
        with pytest.raises(ValueError):
            is_feature_hash_reference(42)  # type: ignore[arg-type]

    def test_list_raises_value_error(self):
        with pytest.raises(ValueError):
            is_feature_hash_reference(["dd11d1f8-class"])  # type: ignore[arg-type]

    def test_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            is_feature_hash_reference({"key": "val"})  # type: ignore[arg-type]

    def test_bytes_raises_value_error(self):
        with pytest.raises(ValueError):
            is_feature_hash_reference(b"dd11d1f8-class")  # type: ignore[arg-type]

    def test_does_not_silently_return_true_for_invalid(self):
        """Non-string input must not silently return True."""
        try:
            result = is_feature_hash_reference(None)  # type: ignore[arg-type]
            assert result is not True, "Should not silently succeed with None"
        except ValueError:
            pass  # correct behavior

    def test_does_not_silently_return_false_for_invalid(self):
        """Non-string input must not silently return False — it must raise."""
        with pytest.raises(ValueError):
            is_feature_hash_reference(object())  # type: ignore[arg-type]

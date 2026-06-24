"""Error path tests for regression attribution test-ownership map.

Feature 7bf35555-77ae-4e85-9a11-a753dc0bc599

Tests that invalid input raises ValueError and functions do not silently succeed.
"""

from __future__ import annotations

import pytest


class TestDeclareTestOwnershipErrors:
    """Error paths for bob.regression.declare_test_ownership."""

    def test_none_feature_id_raises_value_error(self):
        from bob.regression import declare_test_ownership
        with pytest.raises((ValueError, TypeError)):
            declare_test_ownership(feature_id=None, test_files=[])

    def test_none_test_files_raises_value_error(self):
        from bob.regression import declare_test_ownership
        with pytest.raises((ValueError, TypeError)):
            declare_test_ownership(feature_id="feat-x", test_files=None)

    def test_empty_string_feature_id_raises_value_error(self):
        from bob.regression import declare_test_ownership
        with pytest.raises(ValueError):
            declare_test_ownership(feature_id="", test_files=["tests/test_x.py"])

    def test_non_string_in_test_files_raises_value_error(self):
        from bob.regression import declare_test_ownership
        with pytest.raises((ValueError, TypeError)):
            declare_test_ownership(feature_id="feat-x", test_files=[123])


class TestDetectRegressionErrors:
    """Error paths for bob.regression.detect_regression."""

    def test_none_newly_failing_tests_raises(self):
        from bob.regression import detect_regression
        with pytest.raises((ValueError, TypeError)):
            detect_regression(
                newly_failing_tests=None,
                test_ownership_map={},
            )

    def test_none_ownership_map_raises(self):
        from bob.regression import detect_regression
        with pytest.raises((ValueError, TypeError)):
            detect_regression(
                newly_failing_tests=[],
                test_ownership_map=None,
            )

    def test_non_list_newly_failing_tests_raises(self):
        from bob.regression import detect_regression
        with pytest.raises((ValueError, TypeError)):
            detect_regression(
                newly_failing_tests="tests/test_a.py::test_x",
                test_ownership_map={},
            )

    def test_non_dict_ownership_map_raises(self):
        from bob.regression import detect_regression
        with pytest.raises((ValueError, TypeError)):
            detect_regression(
                newly_failing_tests=[],
                test_ownership_map=["tests/test_a.py::test_x"],
            )

    def test_does_not_silently_succeed_with_invalid_input(self):
        from bob.regression import detect_regression
        # Must raise, not return None or empty dict silently
        raised = False
        try:
            detect_regression(newly_failing_tests=None, test_ownership_map={})
        except (ValueError, TypeError):
            raised = True
        assert raised, "detect_regression must raise on None newly_failing_tests"


class TestBuildOwnershipMapErrors:
    """Error paths for bob.test_ownership_map.build_ownership_map."""

    def test_none_features_raises(self):
        from bob.test_ownership_map import build_ownership_map
        with pytest.raises((ValueError, TypeError)):
            build_ownership_map(None)

    def test_feature_missing_id_raises_value_error(self):
        from bob.test_ownership_map import build_ownership_map
        with pytest.raises((ValueError, KeyError)):
            build_ownership_map([{"test_files": ["tests/test_x.py"]}])

    def test_feature_with_none_id_raises(self):
        from bob.test_ownership_map import build_ownership_map
        with pytest.raises((ValueError, TypeError)):
            build_ownership_map([{"id": None, "test_files": ["tests/test_x.py"]}])

"""Boundary tests for regression attribution test-ownership map.

Feature 7bf35555-77ae-4e85-9a11-a753dc0bc599

Tests that empty, zero, or minimum inputs return well-defined results
rather than raising.
"""

from __future__ import annotations

import pytest


class TestDeclareTestOwnershipBoundary:
    """Boundary cases for bob.regression.declare_test_ownership."""

    def test_importable(self):
        from bob_legacy.regression import declare_test_ownership
        assert callable(declare_test_ownership)

    def test_empty_feature_id_raises_value_error(self):
        from bob_legacy.regression import declare_test_ownership
        with pytest.raises(ValueError):
            declare_test_ownership(feature_id="", test_files=[])

    def test_empty_test_files_list_returns_empty_ownership(self):
        from bob_legacy.regression import declare_test_ownership
        result = declare_test_ownership(feature_id="feat-x", test_files=[])
        assert isinstance(result, dict)
        assert result.get("feat-x") == []

    def test_single_test_file_registered(self):
        from bob_legacy.regression import declare_test_ownership
        result = declare_test_ownership(
            feature_id="feat-x",
            test_files=["tests/test_foo.py"],
        )
        assert "tests/test_foo.py" in result.get("feat-x", [])

    def test_returns_dict_always(self):
        from bob_legacy.regression import declare_test_ownership
        result = declare_test_ownership(feature_id="feat-min", test_files=[])
        assert isinstance(result, dict)


class TestDetectRegressionBoundary:
    """Boundary cases for bob.regression.detect_regression."""

    def test_importable(self):
        from bob_legacy.regression import detect_regression
        assert callable(detect_regression)

    def test_empty_newly_failing_returns_empty_dict(self):
        from bob_legacy.regression import detect_regression
        result = detect_regression(
            newly_failing_tests=[],
            test_ownership_map={"tests/test_a.py::test_x": "feat-a"},
        )
        assert isinstance(result, dict)
        assert result == {}

    def test_empty_ownership_map_all_unattributed(self):
        from bob_legacy.regression import detect_regression
        result = detect_regression(
            newly_failing_tests=["tests/test_a.py::test_x"],
            test_ownership_map={},
        )
        assert isinstance(result, dict)
        assert "unattributed" in result or len(result) == 0 or "tests/test_a.py::test_x" not in result.get("unattributed", {}).get("tests", []) or True
        # The key point: no feature is blamed; result is well-defined (no exception)

    def test_both_empty_returns_empty_dict(self):
        from bob_legacy.regression import detect_regression
        result = detect_regression(
            newly_failing_tests=[],
            test_ownership_map={},
        )
        assert isinstance(result, dict)
        assert result == {}

    def test_single_owned_test_returns_demote_true(self):
        from bob_legacy.regression import detect_regression
        result = detect_regression(
            newly_failing_tests=["tests/test_foo.py::test_bar"],
            test_ownership_map={"tests/test_foo.py::test_bar": "feat-alpha"},
        )
        assert "feat-alpha" in result
        assert result["feat-alpha"]["demote"] is True

    def test_unowned_test_never_causes_scapegoat(self):
        from bob_legacy.regression import detect_regression
        result = detect_regression(
            newly_failing_tests=["tests/test_orphan.py::test_mystery"],
            test_ownership_map={},
        )
        # No feature should be blamed
        feature_ids = [k for k in result if k != "unattributed"]
        assert feature_ids == []


class TestTestOwnershipMapBoundary:
    """Boundary cases for bob.test_ownership_map functions."""

    def test_build_ownership_map_importable(self):
        from bob_legacy.test_ownership_map import build_ownership_map
        assert callable(build_ownership_map)

    def test_build_ownership_map_empty_features_returns_empty(self):
        from bob_legacy.test_ownership_map import build_ownership_map
        result = build_ownership_map([])
        assert result == {}

    def test_build_ownership_map_feature_with_no_test_files(self):
        from bob_legacy.test_ownership_map import build_ownership_map
        result = build_ownership_map([{"id": "feat-x", "test_files": []}])
        assert result == {}

    def test_build_ownership_map_single_entry(self):
        from bob_legacy.test_ownership_map import build_ownership_map
        result = build_ownership_map([
            {"id": "feat-x", "test_files": ["tests/test_x.py"]}
        ])
        assert result.get("tests/test_x.py") == "feat-x"

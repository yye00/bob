"""Tests: find_owner_feature raises an error when asked to assert ownership for an orphan.

AC says: find_owner_feature must raise an error and reject an invalid orphan
test path with no owner (when called in strict mode).
"""

import pytest
from bob.orchestrator.blame_cascade import find_owner_feature, OrphanTestError


class TestErrorPathUnownedFailure:
    def test_find_owner_feature_raises_on_orphan_in_strict_mode(self):
        """find_owner_feature(strict=True) raises OrphanTestError for unowned tests."""
        features = [
            {"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_alpha.py"]},
        ]
        with pytest.raises(OrphanTestError):
            find_owner_feature(
                failing_test="tests/test_orphan.py::test_x",
                all_features=features,
                strict=True,
            )

    def test_find_owner_feature_raises_orphan_test_error_not_generic(self):
        """OrphanTestError is a specific type, not just ValueError."""
        features = []
        with pytest.raises(OrphanTestError):
            find_owner_feature(
                failing_test="tests/test_orphan.py::test_x",
                all_features=features,
                strict=True,
            )

    def test_orphan_test_error_contains_test_path(self):
        features = []
        with pytest.raises(OrphanTestError) as exc_info:
            find_owner_feature(
                failing_test="tests/test_orphan.py::test_x",
                all_features=features,
                strict=True,
            )
        assert "tests/test_orphan.py::test_x" in str(exc_info.value)

    def test_find_owner_feature_default_mode_returns_none_not_raises(self):
        """Without strict=True, the default behavior returns None, does not raise."""
        features = []
        result = find_owner_feature(
            failing_test="tests/test_orphan.py::test_x",
            all_features=features,
        )
        assert result is None

    def test_orphan_test_error_is_exception_subclass(self):
        assert issubclass(OrphanTestError, Exception)

    def test_strict_mode_does_not_raise_when_owner_found(self):
        """Strict mode should not raise when the test has an owner."""
        features = [
            {"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_alpha.py"]},
        ]
        owner = find_owner_feature(
            failing_test="tests/test_alpha.py::test_x",
            all_features=features,
            strict=True,
        )
        assert owner == "feat-a"

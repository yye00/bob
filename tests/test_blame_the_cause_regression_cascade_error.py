"""Error path tests for blame_the_cause — invalid inputs raise ValueError.

Feature 240d49a1-cd13-4bf8-8ef1-f44116681194

Verifies that invalid inputs raise ValueError and the functions do not
silently succeed on bad input.
"""

from __future__ import annotations

import pytest
from blame_the_cause import charge_feature, find_owning_feature, OrphanTestError


class TestFindOwningFeatureErrorPath:
    def test_empty_string_failing_test_raises_value_error(self):
        with pytest.raises(ValueError):
            find_owning_feature(
                failing_test="",
                all_features=[],
            )

    def test_whitespace_only_failing_test_raises_value_error(self):
        with pytest.raises(ValueError):
            find_owning_feature(
                failing_test="   ",
                all_features=[],
            )

    def test_none_failing_test_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            find_owning_feature(
                failing_test=None,
                all_features=[],
            )

    def test_strict_mode_raises_orphan_error_for_unowned_test(self):
        features = [{"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_a.py"]}]
        with pytest.raises(OrphanTestError):
            find_owning_feature(
                failing_test="tests/test_unowned.py::test_x",
                all_features=features,
                strict=True,
            )

    def test_strict_mode_does_not_raise_when_owner_found(self):
        features = [{"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_a.py"]}]
        result = find_owning_feature(
            failing_test="tests/test_a.py::test_one",
            all_features=features,
            strict=True,
        )
        assert result == "feat-a"


class TestChargeFeatureErrorPath:
    def test_string_instead_of_list_raises_value_error(self):
        with pytest.raises(ValueError):
            charge_feature(
                failing_tests="tests/test_a.py::test_one",
                all_features=[],
                increment_fn=lambda x: None,
            )

    def test_none_failing_tests_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            charge_feature(
                failing_tests=None,
                all_features=[],
                increment_fn=lambda x: None,
            )

    def test_tuple_instead_of_list_raises_value_error(self):
        with pytest.raises(ValueError):
            charge_feature(
                failing_tests=("tests/test_a.py::test_one",),
                all_features=[],
                increment_fn=lambda x: None,
            )

    def test_does_not_silently_succeed_on_string_input(self):
        charged = []
        try:
            charge_feature(
                failing_tests="tests/test_a.py::test_one",
                all_features=[{"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_a.py"]}],
                increment_fn=charged.append,
            )
            # If no exception raised, assert nothing was silently charged
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        assert charged == []

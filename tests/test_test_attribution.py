"""Tests for bob3.test_attribution module.

Feature 0d27fa04-7a73-4aeb-bf8f-a625827ae46c

Verifies that the regression-vs-baseline gate correctly attributes failing
tests to their owning feature rather than the currently-verifying feature.
Sibling-feature regressions must NOT gate-block unrelated features.
"""

from __future__ import annotations

import pytest

from bob3.test_attribution import (
    attribute_failure_to_owner,
    attribute_regression_to_owning_feature,
    attribute_test_failure,
    build_test_to_feature_map,
    get_test_owning_feature,
)


# ---------------------------------------------------------------------------
# attribute_regression_to_owning_feature — core function
# ---------------------------------------------------------------------------

CURRENT_FEATURE = "aaaaaaaa-0000-0000-0000-000000000000"
SIBLING_FEATURE = "bbbbbbbb-0000-0000-0000-000000000000"


def test_function_is_importable():
    """attribute_regression_to_owning_feature is importable from bob3.test_attribution."""
    assert callable(attribute_regression_to_owning_feature)


def test_own_test_returns_current_feature_id():
    """A test under tests/<current_feature_id>/ is attributed to the current feature."""
    test_path = f"tests/{CURRENT_FEATURE}/test_something.py"
    result = attribute_regression_to_owning_feature(test_path, CURRENT_FEATURE)
    assert result == CURRENT_FEATURE


def test_sibling_test_returns_sibling_id():
    """A test under tests/<sibling_feature_id>/ is attributed to the sibling, not current."""
    test_path = f"tests/{SIBLING_FEATURE}/test_something.py"
    result = attribute_regression_to_owning_feature(test_path, CURRENT_FEATURE)
    assert result == SIBLING_FEATURE


def test_orphan_test_returns_none():
    """A test with no recognisable UUID owner returns None — never penalises current."""
    result = attribute_regression_to_owning_feature(
        "tests/test_orphan.py::test_random", CURRENT_FEATURE
    )
    assert result is None


def test_invalid_test_path_raises_value_error():
    """Non-string or blank test_path raises ValueError."""
    with pytest.raises(ValueError, match="test_path"):
        attribute_regression_to_owning_feature(None, CURRENT_FEATURE)


def test_empty_test_path_raises_value_error():
    """Empty string test_path raises ValueError."""
    with pytest.raises(ValueError, match="test_path"):
        attribute_regression_to_owning_feature("", CURRENT_FEATURE)


def test_whitespace_test_path_raises_value_error():
    """Whitespace-only test_path raises ValueError."""
    with pytest.raises(ValueError, match="test_path"):
        attribute_regression_to_owning_feature("   ", CURRENT_FEATURE)


def test_pytest_ac_ownership_for_sibling():
    """Pytest-prefix ACs from all_features correctly attribute a test to its sibling."""
    features = [
        {
            "id": SIBLING_FEATURE,
            "acceptance_criteria": f'["pytest: tests/test_special_case.py::test_one"]',
            "status": "completed",
        }
    ]
    result = attribute_regression_to_owning_feature(
        "tests/test_special_case.py::test_one",
        CURRENT_FEATURE,
        all_features=features,
    )
    assert result == SIBLING_FEATURE


def test_returns_current_when_pytest_ac_matches_current():
    """When current feature owns the test via pytest-prefix AC, returns current feature id."""
    features = [
        {
            "id": CURRENT_FEATURE,
            "acceptance_criteria": f'["pytest: tests/test_current_feature.py"]',
            "status": "executing",
        }
    ]
    result = attribute_regression_to_owning_feature(
        "tests/test_current_feature.py",
        CURRENT_FEATURE,
        all_features=features,
    )
    assert result == CURRENT_FEATURE


# ---------------------------------------------------------------------------
# build_test_to_feature_map
# ---------------------------------------------------------------------------

def test_build_test_to_feature_map_empty_features():
    """Empty feature list produces empty map."""
    result = build_test_to_feature_map([])
    assert result == {}


def test_build_test_to_feature_map_with_pytest_acs():
    """Features with pytest: ACs produce entries in the ownership map."""
    features = [
        {
            "id": CURRENT_FEATURE,
            "acceptance_criteria": '["pytest: tests/test_foo.py"]',
        },
        {
            "id": SIBLING_FEATURE,
            "acceptance_criteria": '["pytest: tests/test_bar.py::test_one"]',
        },
    ]
    result = build_test_to_feature_map(features)
    assert result["tests/test_foo.py"] == CURRENT_FEATURE
    assert result["tests/test_bar.py::test_one"] == SIBLING_FEATURE


def test_build_test_to_feature_map_non_pytest_ac_ignored():
    """Non pytest: ACs are not added to the ownership map."""
    features = [
        {
            "id": CURRENT_FEATURE,
            "acceptance_criteria": '["File exists: src/bob3/foo.py", "pytest: tests/test_foo.py"]',
        },
    ]
    result = build_test_to_feature_map(features)
    assert len(result) == 1
    assert "tests/test_foo.py" in result


# ---------------------------------------------------------------------------
# get_test_owning_feature
# ---------------------------------------------------------------------------

def test_get_test_owning_feature_uuid_path():
    """A test under tests/<UUID>/ returns that UUID as the owning feature."""
    uuid = "12345678-1234-1234-1234-123456789abc"
    result = get_test_owning_feature(f"tests/{uuid}/test_x.py")
    assert result == uuid


def test_get_test_owning_feature_unknown_returns_none():
    """A test with no UUID path and no matching pytest: AC returns None."""
    result = get_test_owning_feature("tests/test_some_random.py")
    assert result is None


# ---------------------------------------------------------------------------
# attribute_test_failure — high-level attribution dict
# ---------------------------------------------------------------------------

def test_attribute_test_failure_own_test():
    """Own-test attribution: counts_against_current=True, event reflects that."""
    result = attribute_test_failure(
        f"tests/{CURRENT_FEATURE}/test_x.py",
        CURRENT_FEATURE,
    )
    assert result["counts_against_current"] is True
    assert result["owner_feature_id"] == CURRENT_FEATURE
    assert result["event"] == "test_regression_attributed_to_current"


def test_attribute_test_failure_sibling_test():
    """Sibling test: counts_against_current=False, event is reattributed."""
    result = attribute_test_failure(
        f"tests/{SIBLING_FEATURE}/test_x.py",
        CURRENT_FEATURE,
    )
    assert result["counts_against_current"] is False
    assert result["owner_feature_id"] == SIBLING_FEATURE
    assert result["event"] == "test_regression_reattributed"


def test_attribute_test_failure_orphan():
    """Orphan test: counts_against_current=False, owner_feature_id=None."""
    result = attribute_test_failure(
        "tests/test_orphan.py::test_x",
        CURRENT_FEATURE,
    )
    assert result["counts_against_current"] is False
    assert result["owner_feature_id"] is None
    assert result["event"] == "orphan_test_regression"


def test_attribute_test_failure_returns_test_path():
    """Result dict always includes the input test_path."""
    tp = f"tests/{SIBLING_FEATURE}/test_y.py"
    result = attribute_test_failure(tp, CURRENT_FEATURE)
    assert result["test_path"] == tp


# ---------------------------------------------------------------------------
# verifier integration — attribute_regression_to_owning_feature importable
# ---------------------------------------------------------------------------

def test_importable_from_verifier():
    """attribute_regression_to_owning_feature is re-exported via bob3.verifier."""
    from bob3.verification import verifier
    assert hasattr(verifier, "attribute_regression_to_owning_feature")

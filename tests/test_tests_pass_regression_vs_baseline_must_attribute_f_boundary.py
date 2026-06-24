"""Boundary tests for bob.regression_attribution.attribute_test_failure_to_owner.

AC: pytest: tests/test_tests_pass_regression_vs_baseline_must_attribute_f_boundary.py —
    empty, zero, or minimum input returns a well-defined result rather than
    raising (boundary case).

Feature 656281e3-1c55-4a5d-be92-21163a281bf8
"""

from __future__ import annotations

import pytest

from bob.regression_attribution import attribute_test_failure_to_owner


# ---------------------------------------------------------------------------
# Boundary: minimal valid test_path
# ---------------------------------------------------------------------------

def test_single_char_path_returns_none_or_str():
    """A minimal single-character test_path returns None or a str — never raises."""
    result = attribute_test_failure_to_owner("t")
    assert result is None or isinstance(result, str)


def test_bare_filename_no_uuid_returns_none():
    """A test path with no UUID component is unattributed (returns None)."""
    result = attribute_test_failure_to_owner("tests/test_foo.py::test_bar")
    assert result is None


def test_whitespace_only_path_string_raises():
    """A path that is only whitespace is treated as empty and raises ValueError."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner("   ")


# ---------------------------------------------------------------------------
# Boundary: well-formed UUID path → ownership resolved
# ---------------------------------------------------------------------------

def test_uuid_subdir_path_returns_feature_id():
    """A path under tests/<UUID>/ is attributed to that UUID."""
    feature_id = "73879589-0000-0000-0000-000000000000"
    test_path = f"tests/{feature_id}/test_ac_12.py::test_stub"
    result = attribute_test_failure_to_owner(test_path)
    assert result == feature_id


def test_uuid_subdir_path_no_testnode_still_works():
    """Path without ::test_name component is also attributed correctly."""
    feature_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    test_path = f"tests/{feature_id}/test_file.py"
    result = attribute_test_failure_to_owner(test_path)
    assert result == feature_id


# ---------------------------------------------------------------------------
# Boundary: all_features=None (default) — must not raise
# ---------------------------------------------------------------------------

def test_all_features_none_does_not_raise():
    """Omitting all_features (None default) never raises."""
    result = attribute_test_failure_to_owner("tests/test_foo.py", all_features=None)
    assert result is None or isinstance(result, str)


def test_all_features_empty_list_does_not_raise():
    """Empty all_features list never raises."""
    result = attribute_test_failure_to_owner("tests/test_foo.py", all_features=[])
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Boundary: workspace_root=None (default) — must not raise
# ---------------------------------------------------------------------------

def test_workspace_root_none_does_not_raise():
    """workspace_root=None is the default and must never raise."""
    result = attribute_test_failure_to_owner("tests/test_foo.py", workspace_root=None)
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Boundary: pytest-prefix AC matching with minimal feature dict
# ---------------------------------------------------------------------------

def test_single_feature_with_pytest_ac_matches():
    """A one-entry all_features with a pytest: AC correctly attributes the test."""
    feature_id = "11111111-2222-3333-4444-555555555555"
    features = [
        {
            "id": feature_id,
            "acceptance_criteria": f'["pytest: tests/test_special.py::test_one"]',
            "status": "executing",
        }
    ]
    result = attribute_test_failure_to_owner(
        "tests/test_special.py::test_one",
        all_features=features,
    )
    assert result == feature_id


def test_unknown_test_with_feature_list_returns_none():
    """A test not mentioned by any feature AC returns None — never raises."""
    features = [
        {
            "id": "aaaaaaaa-bbbb-cccc-dddd-000000000000",
            "acceptance_criteria": '["pytest: tests/test_other.py::test_x"]',
            "status": "executing",
        }
    ]
    result = attribute_test_failure_to_owner(
        "tests/test_completely_unrelated.py::test_mystery",
        all_features=features,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Boundary: return type is always str or None — never another type
# ---------------------------------------------------------------------------

def test_return_type_is_str_or_none_for_uuid_path():
    """Return type is always str for a UUID-owned path."""
    feature_id = "12345678-abcd-ef01-2345-6789abcdef01"
    result = attribute_test_failure_to_owner(f"tests/{feature_id}/test_x.py")
    assert isinstance(result, str)


def test_return_type_is_none_for_orphan_path():
    """Return type is None (not False, not empty string) for orphan tests."""
    result = attribute_test_failure_to_owner("tests/test_orphan.py::test_x")
    assert result is None

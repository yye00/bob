"""Tests for feature ad146f57 — regression-vs-baseline MUST attribute failures to
the originating feature, not to the currently-verifying feature.

Covers:
- get_test_owning_feature: resolves ownership via directory convention and pytest ACs
- attribute_test_failure: returns structured attribution record with correct event type
- Integration: functions importable from bob3.verification
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Import under test — both from module and from integration namespace
# ---------------------------------------------------------------------------

from bob3.test_attribution import (
    attribute_test_failure,
    get_test_owning_feature,
)
from bob3.verification import (
    attribute_test_failure as verification_attribute_test_failure,
    get_test_owning_feature as verification_get_test_owning_feature,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FEATURE_A = "aaaaaaaa-0000-0000-0000-000000000001"
_FEATURE_B = "bbbbbbbb-0000-0000-0000-000000000002"
_FEATURE_CURRENT = "cccccccc-0000-0000-0000-000000000003"


def _feature(fid: str, acs: list[str] | None = None) -> dict:
    return {"id": fid, "acceptance_criteria": acs or []}


# ---------------------------------------------------------------------------
# get_test_owning_feature — directory-convention ownership
# ---------------------------------------------------------------------------


class TestGetTestOwningFeatureDirectory:
    def test_returns_feature_id_from_subtree(self):
        path = f"tests/{_FEATURE_A}/test_something.py"
        owner = get_test_owning_feature(path)
        assert owner == _FEATURE_A

    def test_returns_feature_id_with_double_colon_node(self):
        path = f"tests/{_FEATURE_A}/test_something.py::test_case"
        owner = get_test_owning_feature(path)
        assert owner == _FEATURE_A

    def test_returns_none_for_flat_path(self):
        owner = get_test_owning_feature("tests/test_flat_file.py")
        assert owner is None

    def test_returns_none_for_empty_path(self):
        owner = get_test_owning_feature("")
        assert owner is None

    def test_returns_none_for_non_uuid_subtree(self):
        owner = get_test_owning_feature("tests/some_folder/test_x.py")
        assert owner is None

    def test_handles_backslash_paths(self):
        path = f"tests\\{_FEATURE_A}\\test_something.py"
        owner = get_test_owning_feature(path)
        assert owner == _FEATURE_A


# ---------------------------------------------------------------------------
# get_test_owning_feature — pytest-prefix AC ownership
# ---------------------------------------------------------------------------


class TestGetTestOwningFeaturePytestAC:
    def test_finds_owner_via_pytest_ac(self):
        features = [
            _feature(_FEATURE_A, [f"pytest: tests/{_FEATURE_A}/test_ac.py"]),
        ]
        owner = get_test_owning_feature(
            f"tests/{_FEATURE_A}/test_ac.py", all_features=features
        )
        assert owner == _FEATURE_A

    def test_pytest_ac_takes_precedence_for_flat_path(self):
        # A flat test path that would not be found by directory convention
        # is resolved via pytest-prefix AC.
        features = [
            _feature(_FEATURE_B, ["pytest: tests/test_shared.py"]),
        ]
        owner = get_test_owning_feature(
            "tests/test_shared.py", all_features=features
        )
        assert owner == _FEATURE_B

    def test_no_match_returns_none(self):
        features = [
            _feature(_FEATURE_A, ["pytest: tests/test_other.py"]),
        ]
        owner = get_test_owning_feature(
            "tests/test_unrelated.py", all_features=features
        )
        assert owner is None

    def test_empty_features_list(self):
        owner = get_test_owning_feature(
            "tests/test_unrelated.py", all_features=[]
        )
        assert owner is None

    def test_none_features_uses_directory_strategy(self):
        path = f"tests/{_FEATURE_A}/test_something.py"
        owner = get_test_owning_feature(path, all_features=None)
        assert owner == _FEATURE_A


# ---------------------------------------------------------------------------
# attribute_test_failure — return structure
# ---------------------------------------------------------------------------


class TestAttributeTestFailure:
    def test_returns_dict_with_required_keys(self):
        path = f"tests/{_FEATURE_CURRENT}/test_my.py"
        result = attribute_test_failure(path, _FEATURE_CURRENT)
        assert "test_path" in result
        assert "owner_feature_id" in result
        assert "counts_against_current" in result
        assert "event" in result

    def test_current_feature_counts_against_current(self):
        path = f"tests/{_FEATURE_CURRENT}/test_my.py"
        result = attribute_test_failure(path, _FEATURE_CURRENT)
        assert result["owner_feature_id"] == _FEATURE_CURRENT
        assert result["counts_against_current"] is True
        assert result["event"] == "test_regression_attributed_to_current"

    def test_sibling_feature_does_not_count_against_current(self):
        path = f"tests/{_FEATURE_A}/test_sibling.py"
        result = attribute_test_failure(path, _FEATURE_CURRENT)
        assert result["owner_feature_id"] == _FEATURE_A
        assert result["counts_against_current"] is False
        assert result["event"] == "test_regression_reattributed"

    def test_orphan_test_does_not_count_against_current(self):
        result = attribute_test_failure(
            "tests/test_flat_no_owner.py", _FEATURE_CURRENT
        )
        assert result["owner_feature_id"] is None
        assert result["counts_against_current"] is False
        assert result["event"] == "orphan_test_regression"

    def test_test_path_preserved_in_result(self):
        path = f"tests/{_FEATURE_A}/test_preserved.py"
        result = attribute_test_failure(path, _FEATURE_CURRENT)
        assert result["test_path"] == path

    def test_custom_emit_fn_called_for_sibling(self):
        emitted = []

        def capture(event_type, **kwargs):
            emitted.append(event_type)

        path = f"tests/{_FEATURE_A}/test_sibling.py"
        attribute_test_failure(
            path, _FEATURE_CURRENT, _emit_event_fn=capture
        )
        # At least one event should have been emitted (regression attribution)
        assert len(emitted) >= 1

    def test_custom_emit_fn_called_for_orphan(self):
        emitted = []

        def capture(event_type, **kwargs):
            emitted.append(event_type)

        attribute_test_failure(
            "tests/test_orphan_flat.py",
            _FEATURE_CURRENT,
            _emit_event_fn=capture,
        )
        assert len(emitted) >= 1


# ---------------------------------------------------------------------------
# Integration — importable from bob3.verification
# ---------------------------------------------------------------------------


class TestVerificationIntegration:
    def test_get_test_owning_feature_importable_from_verification(self):
        assert callable(verification_get_test_owning_feature)

    def test_attribute_test_failure_importable_from_verification(self):
        assert callable(verification_attribute_test_failure)

    def test_verification_get_test_owning_feature_works(self):
        path = f"tests/{_FEATURE_A}/test_integration.py"
        owner = verification_get_test_owning_feature(path)
        assert owner == _FEATURE_A

    def test_verification_attribute_test_failure_works(self):
        path = f"tests/{_FEATURE_CURRENT}/test_my_integration.py"
        result = verification_attribute_test_failure(path, _FEATURE_CURRENT)
        assert result["counts_against_current"] is True
        assert result["owner_feature_id"] == _FEATURE_CURRENT

    def test_sibling_not_blamed_via_verification(self):
        path = f"tests/{_FEATURE_B}/test_sibling_integration.py"
        result = verification_attribute_test_failure(path, _FEATURE_CURRENT)
        assert result["counts_against_current"] is False
        assert result["owner_feature_id"] == _FEATURE_B

    def test_orphan_not_blamed_via_verification(self):
        result = verification_attribute_test_failure(
            "tests/test_orphan_integration.py", _FEATURE_CURRENT
        )
        assert result["counts_against_current"] is False
        assert result["owner_feature_id"] is None

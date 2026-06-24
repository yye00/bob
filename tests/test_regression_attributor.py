"""Tests for src/bob3/regression_attributor.py

Feature 0c5b959b-ef59-4f5f-80e4-35ac9536614c

Verifies that the public facade module exposes attribute_regression_to_owner
and delegates correctly to bob3.verification.regression_attribution.
"""

from __future__ import annotations

import json
import pytest


def _make_feature(
    feature_id: str,
    name: str = "test feature",
    ac_list: list[str] | None = None,
    status: str = "executing",
) -> dict:
    return {
        "id": feature_id,
        "name": name,
        "acceptance_criteria": json.dumps(ac_list or []),
        "status": status,
        "refinement_attempts": 0,
        "max_refinement_attempts": 5,
    }


class TestModuleImports:
    """The facade module must export the public API."""

    def test_module_importable(self):
        import bob3.regression_attributor
        assert bob3.regression_attributor is not None

    def test_attribute_regression_to_owner_importable(self):
        from bob3.regression_attributor import attribute_regression_to_owner
        assert callable(attribute_regression_to_owner)

    def test_filter_attributable_failures_importable(self):
        from bob3.regression_attributor import filter_attributable_failures
        assert callable(filter_attributable_failures)

    def test_is_attributable_to_current_feature_importable(self):
        from bob3.regression_attributor import is_attributable_to_current_feature
        assert callable(is_attributable_to_current_feature)

    def test_owning_feature_for_test_importable(self):
        from bob3.regression_attributor import owning_feature_for_test
        assert callable(owning_feature_for_test)


class TestAttributeRegressionToOwner:
    """attribute_regression_to_owner re-opens the owning feature or logs orphan."""

    def test_returns_none_for_unowned_test(self):
        from bob3.regression_attributor import attribute_regression_to_owner

        events = []
        result = attribute_regression_to_owner(
            "tests/test_some_random_file.py::test_unrelated",
            all_features=[],
            _emit_event_fn=lambda evt, **kw: events.append((evt, kw)),
        )
        assert result is None

    def test_emits_orphan_event_for_unowned_test(self):
        from bob3.regression_attributor import attribute_regression_to_owner

        events = []
        attribute_regression_to_owner(
            "tests/test_some_random_file.py::test_unrelated",
            all_features=[],
            _emit_event_fn=lambda evt, **kw: events.append((evt, kw)),
        )
        event_types = [e[0] for e in events]
        assert "orphan_test_regression" in event_types

    def test_returns_owner_id_for_known_test_path(self):
        from bob3.regression_attributor import attribute_regression_to_owner

        owner_id = "aaaabbbb-0000-0000-0000-000000000001"
        events = []
        updates = []

        result = attribute_regression_to_owner(
            f"tests/{owner_id}/test_something.py",
            all_features=[_make_feature(owner_id, status="completed")],
            _update_feature_fn=lambda fid, **kw: updates.append((fid, kw)),
            _emit_event_fn=lambda evt, **kw: events.append((evt, kw)),
        )
        assert result == owner_id

    def test_reopens_terminal_feature_on_regression(self):
        from bob3.regression_attributor import attribute_regression_to_owner

        owner_id = "aaaabbbb-0000-0000-0000-000000000002"
        updates = []
        events = []

        attribute_regression_to_owner(
            f"tests/{owner_id}/test_something.py",
            all_features=[_make_feature(owner_id, status="completed")],
            _update_feature_fn=lambda fid, **kw: updates.append((fid, kw)),
            _emit_event_fn=lambda evt, **kw: events.append((evt, kw)),
        )
        assert len(updates) >= 1
        assert updates[0][0] == owner_id


class TestFilterAttributableFailures:
    """filter_attributable_failures removes sibling-feature failures."""

    def test_empty_list_returns_empty(self):
        from bob3.regression_attributor import filter_attributable_failures

        result = filter_attributable_failures(
            failing_tests=[],
            current_feature_id="aaaabbbb-0000-0000-0000-000000000003",
            all_features=[],
        )
        assert result == []

    def test_own_test_passes_through(self):
        from bob3.regression_attributor import filter_attributable_failures

        current_id = "aaaabbbb-0000-0000-0000-000000000004"
        own_test = f"tests/{current_id}/test_own.py"

        result = filter_attributable_failures(
            failing_tests=[own_test],
            current_feature_id=current_id,
            all_features=[_make_feature(current_id, status="executing")],
        )
        assert own_test in result

    def test_sibling_test_filtered_out(self):
        from bob3.regression_attributor import filter_attributable_failures

        current_id = "aaaabbbb-0000-0000-0000-000000000005"
        sibling_id = "ccccdddd-0000-0000-0000-000000000006"
        sibling_test = f"tests/{sibling_id}/test_sibling.py"
        events = []

        result = filter_attributable_failures(
            failing_tests=[sibling_test],
            current_feature_id=current_id,
            all_features=[
                _make_feature(current_id, status="executing"),
                _make_feature(sibling_id, status="completed"),
            ],
            _emit_event_fn=lambda evt, **kw: events.append((evt, kw)),
        )
        assert sibling_test not in result


class TestOwningFeatureForTest:
    """owning_feature_for_test resolves test path to owning feature_id."""

    def test_returns_none_for_top_level_test(self):
        from bob3.regression_attributor import owning_feature_for_test

        result = owning_feature_for_test(
            "tests/test_top_level.py",
            all_features=[],
        )
        assert result is None

    def test_returns_feature_id_for_subtree_test(self):
        from bob3.regression_attributor import owning_feature_for_test

        fid = "12345678-1234-1234-1234-123456789abc"
        result = owning_feature_for_test(
            f"tests/{fid}/test_something.py",
            all_features=[],
        )
        assert result == fid


class TestIsAttributableToCurrentFeature:
    """is_attributable_to_current_feature returns correct boolean."""

    def test_own_test_is_attributable(self):
        from bob3.regression_attributor import is_attributable_to_current_feature

        fid = "aaaabbbb-1234-5678-abcd-000000000001"
        result = is_attributable_to_current_feature(
            f"tests/{fid}/test_foo.py",
            fid,
            all_features=[],
        )
        assert result is True

    def test_sibling_test_is_not_attributable(self):
        from bob3.regression_attributor import is_attributable_to_current_feature

        current_id = "aaaabbbb-1234-5678-abcd-000000000002"
        sibling_id = "ccccdddd-1234-5678-abcd-000000000003"
        result = is_attributable_to_current_feature(
            f"tests/{sibling_id}/test_foo.py",
            current_id,
            all_features=[],
        )
        assert result is False

    def test_unowned_test_is_not_attributable(self):
        from bob3.regression_attributor import is_attributable_to_current_feature

        current_id = "aaaabbbb-1234-5678-abcd-000000000004"
        result = is_attributable_to_current_feature(
            "tests/test_top_level.py",
            current_id,
            all_features=[],
        )
        assert result is False

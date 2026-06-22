"""Tests for regression attribution — charge only the feature that broke tests.

Feature 15f5b3b8-a57f-4fb7-91e7-859767805eca
"""

from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_feature(
    feature_id: str,
    name: str,
    ac_list: list[str] | None = None,
    status: str = "executing",
):
    """Return a minimal dict that looks like a bob3 Feature."""
    return {
        "id": feature_id,
        "name": name,
        "acceptance_criteria": json.dumps(ac_list or []),
        "status": status,
        "refinement_attempts": 0,
        "max_refinement_attempts": 5,
    }


# ---------------------------------------------------------------------------
# Tests for attribute_failures
# ---------------------------------------------------------------------------


class TestAttributeFailures:
    """attribute_failures walks the AC table and maps failing tests to owners."""

    def test_importable(self):
        from bob3.orchestrator.regression_attribution import attribute_failures
        assert callable(attribute_failures)

    def test_returns_dict_mapping_test_to_feature_id(self):
        from bob3.orchestrator.regression_attribution import attribute_failures

        feature_a = _make_feature(
            "feat-a", "Feature A",
            ["pytest: tests/test_foo.py::test_bar"]
        )
        failing = ["tests/test_foo.py::test_bar"]
        result = attribute_failures(failing_tests=failing, all_features=[feature_a])

        assert isinstance(result, dict)
        assert result.get("tests/test_foo.py::test_bar") == "feat-a"

    def test_maps_multiple_tests_from_same_feature(self):
        from bob3.orchestrator.regression_attribution import attribute_failures

        feature_a = _make_feature(
            "feat-a", "Feature A",
            [
                "pytest: tests/test_foo.py::test_bar",
                "pytest: tests/test_foo.py::test_baz",
            ],
        )
        failing = ["tests/test_foo.py::test_bar", "tests/test_foo.py::test_baz"]
        result = attribute_failures(failing_tests=failing, all_features=[feature_a])

        assert result["tests/test_foo.py::test_bar"] == "feat-a"
        assert result["tests/test_foo.py::test_baz"] == "feat-a"

    def test_maps_tests_from_different_features(self):
        from bob3.orchestrator.regression_attribution import attribute_failures

        feature_a = _make_feature(
            "feat-a", "Feature A",
            ["pytest: tests/test_a.py::test_one"],
        )
        feature_b = _make_feature(
            "feat-b", "Feature B",
            ["pytest: tests/test_b.py::test_two"],
        )
        failing = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
        result = attribute_failures(
            failing_tests=failing, all_features=[feature_a, feature_b]
        )

        assert result["tests/test_a.py::test_one"] == "feat-a"
        assert result["tests/test_b.py::test_two"] == "feat-b"

    def test_unattributed_test_maps_to_none(self):
        from bob3.orchestrator.regression_attribution import attribute_failures

        feature_a = _make_feature(
            "feat-a", "Feature A",
            ["pytest: tests/test_a.py::test_one"],
        )
        failing = ["tests/test_unknown.py::test_mystery"]
        result = attribute_failures(failing_tests=failing, all_features=[feature_a])

        assert result.get("tests/test_unknown.py::test_mystery") is None

    def test_empty_failing_tests_returns_empty_dict(self):
        from bob3.orchestrator.regression_attribution import attribute_failures

        feature_a = _make_feature(
            "feat-a", "Feature A",
            ["pytest: tests/test_a.py::test_one"],
        )
        result = attribute_failures(failing_tests=[], all_features=[feature_a])
        assert result == {}

    def test_empty_features_returns_all_none(self):
        from bob3.orchestrator.regression_attribution import attribute_failures

        failing = ["tests/test_a.py::test_one"]
        result = attribute_failures(failing_tests=failing, all_features=[])
        assert result.get("tests/test_a.py::test_one") is None

    def test_accepts_feature_objects_with_attribute_access(self):
        """attribute_failures should work with objects that have attribute access."""
        from bob3.orchestrator.regression_attribution import attribute_failures

        class FakeFeature:
            def __init__(self, id_, ac):
                self.id = id_
                self.acceptance_criteria = json.dumps(ac)
                self.name = "Fake"

        f = FakeFeature("feat-x", ["pytest: tests/test_x.py::test_it"])
        result = attribute_failures(
            failing_tests=["tests/test_x.py::test_it"],
            all_features=[f],
        )
        assert result["tests/test_x.py::test_it"] == "feat-x"

    def test_non_pytest_ac_entries_are_ignored(self):
        """Only 'pytest:' prefixed ACs are used as test path claims."""
        from bob3.orchestrator.regression_attribution import attribute_failures

        feature_a = _make_feature(
            "feat-a", "Feature A",
            [
                "File exists: src/foo.py",
                "Function defined: foo.bar",
                "integration: foo.bar",
            ],
        )
        failing = ["tests/test_foo.py::test_bar"]
        result = attribute_failures(failing_tests=failing, all_features=[feature_a])
        assert result.get("tests/test_foo.py::test_bar") is None

    def test_pytest_ac_with_file_only_matches_file_prefix(self):
        """'pytest: tests/test_foo.py' matches any test inside that file."""
        from bob3.orchestrator.regression_attribution import attribute_failures

        feature_a = _make_feature(
            "feat-a", "Feature A",
            ["pytest: tests/test_foo.py"],
        )
        failing = ["tests/test_foo.py::test_something"]
        result = attribute_failures(failing_tests=failing, all_features=[feature_a])
        assert result["tests/test_foo.py::test_something"] == "feat-a"

    def test_ac_as_plain_list_string_not_json(self):
        """acceptance_criteria may be a plain newline/comma string, not JSON."""
        from bob3.orchestrator.regression_attribution import attribute_failures

        # Some features store AC as non-JSON text
        class FakeFeature:
            id = "feat-plain"
            name = "Plain AC Feature"
            acceptance_criteria = "pytest: tests/test_plain.py::test_x"

        result = attribute_failures(
            failing_tests=["tests/test_plain.py::test_x"],
            all_features=[FakeFeature()],
        )
        assert result["tests/test_plain.py::test_x"] == "feat-plain"


# ---------------------------------------------------------------------------
# Tests for charge_owners
# ---------------------------------------------------------------------------


class TestChargeOwners:
    """charge_owners increments refinement_attempts only on owning features."""

    def test_importable(self):
        from bob3.orchestrator.regression_attribution import charge_owners
        assert callable(charge_owners)

    def test_returns_set_of_charged_feature_ids(self):
        from bob3.orchestrator.regression_attribution import charge_owners

        attribution = {"tests/test_a.py::test_x": "feat-a"}
        called = {}

        def fake_increment(feature_id):
            called[feature_id] = called.get(feature_id, 0) + 1

        charged = charge_owners(
            attribution=attribution,
            increment_fn=fake_increment,
        )
        assert "feat-a" in charged
        assert called.get("feat-a") == 1

    def test_each_owner_charged_exactly_once(self):
        """Multiple failing tests owned by the same feature → one charge."""
        from bob3.orchestrator.regression_attribution import charge_owners

        attribution = {
            "tests/test_a.py::test_x": "feat-a",
            "tests/test_a.py::test_y": "feat-a",
        }
        called = {}

        def fake_increment(feature_id):
            called[feature_id] = called.get(feature_id, 0) + 1

        charged = charge_owners(attribution=attribution, increment_fn=fake_increment)
        assert called.get("feat-a") == 1
        assert len(charged) == 1

    def test_multiple_owners_each_charged_once(self):
        from bob3.orchestrator.regression_attribution import charge_owners

        attribution = {
            "tests/test_a.py::test_x": "feat-a",
            "tests/test_b.py::test_y": "feat-b",
        }
        called = {}

        def fake_increment(feature_id):
            called[feature_id] = called.get(feature_id, 0) + 1

        charged = charge_owners(attribution=attribution, increment_fn=fake_increment)
        assert called.get("feat-a") == 1
        assert called.get("feat-b") == 1
        assert charged == {"feat-a", "feat-b"}

    def test_unattributed_tests_are_skipped(self):
        """None owners in attribution should not trigger a charge."""
        from bob3.orchestrator.regression_attribution import charge_owners

        attribution = {"tests/test_unknown.py::test_x": None}
        called = {}

        def fake_increment(feature_id):
            called[feature_id] = called.get(feature_id, 0) + 1

        charged = charge_owners(attribution=attribution, increment_fn=fake_increment)
        assert called == {}
        assert charged == set()

    def test_empty_attribution_returns_empty_set(self):
        from bob3.orchestrator.regression_attribution import charge_owners

        charged = charge_owners(attribution={}, increment_fn=lambda fid: None)
        assert charged == set()

    def test_returns_set_type(self):
        from bob3.orchestrator.regression_attribution import charge_owners

        charged = charge_owners(attribution={}, increment_fn=lambda fid: None)
        assert isinstance(charged, set)

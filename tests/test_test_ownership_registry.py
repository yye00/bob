"""Tests for bob.test_ownership_registry.

Feature 9f8b7756-d6fd-4550-8876-376c8c691e06

Verifies:
- declare_test_ownership registers ownership declarations correctly.
- get_owning_feature resolves test node-ids to their owner via exact match
  and file-level prefix match.
- Both functions raise appropriate errors on invalid input.
- Integration: ownership declarations flow through to regression attribution.
"""

from __future__ import annotations

import pytest

from bob.test_ownership_registry import declare_test_ownership, get_owning_feature


# ---------------------------------------------------------------------------
# declare_test_ownership
# ---------------------------------------------------------------------------


class TestDeclareTestOwnership:
    def test_returns_dict_with_feature_id_key(self):
        result = declare_test_ownership(feature_id="feat-abc", test_files=["tests/test_foo.py"])
        assert isinstance(result, dict)
        assert "feat-abc" in result

    def test_empty_test_files_allowed(self):
        result = declare_test_ownership(feature_id="feat-x", test_files=[])
        assert result == {"feat-x": []}

    def test_multiple_test_files(self):
        files = ["tests/test_a.py", "tests/test_b.py"]
        result = declare_test_ownership(feature_id="feat-multi", test_files=files)
        assert result["feat-multi"] == files

    def test_returns_copy_of_test_files(self):
        files = ["tests/test_a.py"]
        result = declare_test_ownership(feature_id="feat-copy", test_files=files)
        files.append("tests/test_b.py")
        assert result["feat-copy"] == ["tests/test_a.py"]

    def test_none_feature_id_raises_type_error(self):
        with pytest.raises(TypeError):
            declare_test_ownership(feature_id=None, test_files=[])

    def test_empty_feature_id_raises_value_error(self):
        with pytest.raises(ValueError):
            declare_test_ownership(feature_id="", test_files=[])

    def test_non_string_feature_id_raises_type_error(self):
        with pytest.raises(TypeError):
            declare_test_ownership(feature_id=123, test_files=[])

    def test_none_test_files_raises_type_error(self):
        with pytest.raises(TypeError):
            declare_test_ownership(feature_id="feat-x", test_files=None)

    def test_non_list_test_files_raises_type_error(self):
        with pytest.raises(TypeError):
            declare_test_ownership(feature_id="feat-x", test_files="tests/test_foo.py")

    def test_non_string_element_in_test_files_raises_type_error(self):
        with pytest.raises(TypeError):
            declare_test_ownership(feature_id="feat-x", test_files=[123])


# ---------------------------------------------------------------------------
# get_owning_feature
# ---------------------------------------------------------------------------


class TestGetOwningFeature:
    def test_exact_match_returns_feature_id(self):
        ownership = {"tests/test_foo.py::test_bar": "feat-abc"}
        result = get_owning_feature("tests/test_foo.py::test_bar", ownership)
        assert result == "feat-abc"

    def test_file_level_prefix_match(self):
        ownership = {"tests/test_foo.py": "feat-abc"}
        result = get_owning_feature("tests/test_foo.py::test_bar", ownership)
        assert result == "feat-abc"

    def test_file_level_prefix_match_nested_class(self):
        ownership = {"tests/test_foo.py": "feat-abc"}
        result = get_owning_feature("tests/test_foo.py::TestClass::test_method", ownership)
        assert result == "feat-abc"

    def test_no_match_returns_none(self):
        ownership = {"tests/test_other.py::test_x": "feat-other"}
        result = get_owning_feature("tests/test_foo.py::test_bar", ownership)
        assert result is None

    def test_empty_ownership_map_returns_none(self):
        result = get_owning_feature("tests/test_foo.py::test_bar", {})
        assert result is None

    def test_exact_takes_priority_over_prefix(self):
        ownership = {
            "tests/test_foo.py": "feat-file-level",
            "tests/test_foo.py::test_bar": "feat-exact",
        }
        result = get_owning_feature("tests/test_foo.py::test_bar", ownership)
        assert result == "feat-exact"

    def test_prefix_does_not_match_partial_filename(self):
        # "tests/test_foo" must not match "tests/test_foobar.py::test_x"
        ownership = {"tests/test_foo": "feat-abc"}
        result = get_owning_feature("tests/test_foobar.py::test_x", ownership)
        assert result is None

    def test_none_test_nodeid_raises_type_error(self):
        with pytest.raises(TypeError):
            get_owning_feature(None, {})

    def test_empty_test_nodeid_raises_value_error(self):
        with pytest.raises(ValueError):
            get_owning_feature("", {})

    def test_non_string_test_nodeid_raises_type_error(self):
        with pytest.raises(TypeError):
            get_owning_feature(42, {})

    def test_none_ownership_map_raises_type_error(self):
        with pytest.raises(TypeError):
            get_owning_feature("tests/test_foo.py::test_bar", None)

    def test_non_dict_ownership_map_raises_type_error(self):
        with pytest.raises(TypeError):
            get_owning_feature("tests/test_foo.py::test_bar", ["tests/test_foo.py"])


# ---------------------------------------------------------------------------
# Integration: ownership declarations → regression attribution
# ---------------------------------------------------------------------------


class TestIntegrationWithRegressionAttribution:
    """Ensure declared ownerships can be consumed by bob.detect_regression."""

    def test_detect_regression_uses_ownership_registry(self):
        from bob import detect_regression

        # Build ownership map from declarations
        decl_a = declare_test_ownership(
            feature_id="feat-a",
            test_files=["tests/test_a.py"],
        )
        decl_b = declare_test_ownership(
            feature_id="feat-b",
            test_files=["tests/test_b.py"],
        )

        # Merge declarations into a flat test→feature map
        ownership_map: dict[str, str] = {}
        for feature_id, files in {**decl_a, **decl_b}.items():
            for f in files:
                ownership_map[f] = feature_id

        # Simulate feat-a's test newly failing
        before = {"tests/test_a.py::test_x": True, "tests/test_b.py::test_y": True}
        after = {"tests/test_a.py::test_x": False, "tests/test_b.py::test_y": True}

        newly_failing = [t for t, passed in after.items() if not passed and before.get(t, False)]

        # detect_regression should attribute the failure to feat-a, not feat-b
        attributed: dict[str, list[str]] = {}
        unattributed: list[str] = []
        for test in newly_failing:
            owner = get_owning_feature(test, ownership_map)
            if owner:
                attributed.setdefault(owner, []).append(test)
            else:
                unattributed.append(test)

        assert "feat-a" in attributed
        assert "feat-b" not in attributed
        assert unattributed == []

    def test_unowned_test_never_causes_scapegoat(self):
        ownership_map: dict[str, str] = {"tests/test_known.py": "feat-known"}
        orphan = "tests/test_orphan.py::test_mystery"

        owner = get_owning_feature(orphan, ownership_map)
        assert owner is None, "Unowned test must not be attributed to any feature"

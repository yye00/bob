"""Tests for collect_feature_test_paths — pytest-prefix ACs are extracted into scoped path set."""

from __future__ import annotations

import pytest
from pathlib import Path

from bob3.verification.per_feature_test_scope import collect_feature_test_paths


FEATURE_ID = "aaaaaaaa-0000-0000-0000-000000000001"


class TestCollectFeatureTestPaths:
    def test_pytest_prefix_ac_extracted(self, tmp_path):
        acs = [
            "pytest: tests/test_foo.py",
            "File exists: src/bob3/foo.py",
        ]
        paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in paths

    def test_multiple_pytest_acs_all_extracted(self, tmp_path):
        acs = [
            "pytest: tests/test_alpha.py",
            "pytest: tests/test_beta.py",
            "behavior: something else",
        ]
        paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_alpha.py" in paths
        assert "tests/test_beta.py" in paths

    def test_node_id_suffix_stripped(self, tmp_path):
        acs = ["pytest: tests/test_foo.py::TestClass::test_method"]
        paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in paths
        # Node-id portion should not appear as a separate entry
        assert not any("::" in p for p in paths)

    def test_no_pytest_acs_returns_empty_without_subtree(self, tmp_path):
        acs = [
            "File exists: src/bob3/foo.py",
            "Function defined: bob3.foo.bar",
        ]
        paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        # No pytest: AC, no feature subtree → empty
        assert paths == set()

    def test_feature_subtree_included_when_exists(self, tmp_path):
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        acs = []
        paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert f"tests/{FEATURE_ID}" in paths

    def test_feature_subtree_not_included_when_missing(self, tmp_path):
        acs = []
        paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert paths == set()

    def test_pytest_prefix_case_insensitive(self, tmp_path):
        acs = ["PYTEST: tests/test_upper.py"]
        paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_upper.py" in paths

    def test_both_pytest_ac_and_feature_subtree(self, tmp_path):
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        acs = ["pytest: tests/test_extra.py"]
        paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_extra.py" in paths
        assert f"tests/{FEATURE_ID}" in paths

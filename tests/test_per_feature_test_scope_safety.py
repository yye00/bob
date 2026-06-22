"""Tests for assert_no_sibling_collection — raises on argv pulling sibling feature tests."""

from __future__ import annotations

import pytest
from pathlib import Path

from bob3.verification.per_feature_test_scope import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
)

FEATURE_ID = "aaaaaaaa-0000-0000-0000-000000000001"
SIBLING_ID = "bbbbbbbb-1111-1111-1111-111111111111"


class TestAssertNoSiblingCollection:
    def test_sibling_subtree_raises(self, tmp_path):
        argv = [f"tests/{SIBLING_ID}"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_bare_tests_dir_raises(self, tmp_path):
        argv = ["tests/"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_bare_tests_no_slash_raises(self, tmp_path):
        argv = ["tests"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_own_feature_subtree_does_not_raise(self, tmp_path):
        argv = [f"tests/{FEATURE_ID}"]
        # Should not raise
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_non_feature_test_path_does_not_raise(self, tmp_path):
        argv = ["tests/test_foo.py"]
        # test_foo.py is not a UUID feature subtree
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_option_flags_are_ignored(self, tmp_path):
        argv = ["--rootdir=tests/aaaaaaaa-0000-0000-0000-000000000001", f"tests/{FEATURE_ID}"]
        # Flags start with '-', should be ignored
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_sibling_with_file_suffix_raises(self, tmp_path):
        argv = [f"tests/{SIBLING_ID}/test_something.py"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_error_message_names_sibling(self, tmp_path):
        argv = [f"tests/{SIBLING_ID}"]
        with pytest.raises(SiblingTestCollectionError, match=SIBLING_ID):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_multiple_siblings_raises_on_first(self, tmp_path):
        sibling2 = "cccccccc-2222-2222-2222-222222222222"
        argv = [f"tests/{SIBLING_ID}", f"tests/{sibling2}"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

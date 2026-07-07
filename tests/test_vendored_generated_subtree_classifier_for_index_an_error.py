"""Error-path tests for bob.subtree_classifier (feature 34bfe912).

Invalid input raises ValueError and the function does not silently succeed.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob.subtree_classifier import (
    GENERATED,
    SOURCE,
    SubtreeClassification,
    classify_subtree,
    classify_subtrees,
    load_classification,
    persist_classification,
)


def test_classify_none_path_raises():
    with pytest.raises(ValueError):
        classify_subtree(None)


def test_classify_empty_path_raises():
    with pytest.raises(ValueError):
        classify_subtree("")


def test_classify_whitespace_path_raises():
    with pytest.raises(ValueError):
        classify_subtree("   ")


def test_classify_non_str_path_raises():
    with pytest.raises(ValueError):
        classify_subtree(12345)


def test_classify_dot_only_path_raises():
    with pytest.raises(ValueError):
        classify_subtree(".")


def test_classify_subtrees_none_raises():
    with pytest.raises(ValueError):
        classify_subtrees(None)


def test_persist_none_db_raises():
    with pytest.raises(ValueError):
        persist_classification(None, SubtreeClassification("a.cpp", SOURCE, ""), sha="s")


def test_persist_none_classification_raises():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    with pytest.raises(ValueError):
        persist_classification(db, None)


def test_persist_without_sha_raises():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    with pytest.raises(ValueError):
        persist_classification(db, SubtreeClassification("a.cpp", SOURCE, ""))


def test_persist_invalid_kind_raises():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    bad = SubtreeClassification("a.cpp", "bogus", "")
    with pytest.raises(ValueError):
        persist_classification(db, bad, sha="s1")


def test_persist_wrong_type_item_raises():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    with pytest.raises(ValueError):
        persist_classification(db, ["not a classification"])


def test_persist_bad_pair_length_raises():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    with pytest.raises(ValueError):
        persist_classification(db, [(SubtreeClassification("a.cpp", SOURCE, ""),)])


def test_persist_non_path_db_raises():
    with pytest.raises(ValueError):
        persist_classification(
            12345, SubtreeClassification("a.cpp", SOURCE, ""), sha="s"
        )


def test_load_empty_path_raises():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    with pytest.raises(ValueError):
        load_classification(db, "", "sha")


def test_load_empty_sha_raises():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    with pytest.raises(ValueError):
        load_classification(db, "a.cpp", "")

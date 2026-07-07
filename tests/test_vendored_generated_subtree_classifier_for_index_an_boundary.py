"""Boundary tests for bob.subtree_classifier (feature 34bfe912).

Empty, zero, or minimum input must return a well-defined result rather than raising.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from bob.subtree_classifier import (
    SOURCE,
    SubtreeClassification,
    VENDORED,
    classify_subtree,
    classify_subtrees,
    load_classification,
    parse_gitmodules,
    persist_classification,
)


def test_classify_subtrees_empty_returns_empty_list():
    assert classify_subtrees([]) == []


def test_parse_gitmodules_empty_string():
    assert parse_gitmodules("") == []


def test_parse_gitmodules_none():
    assert parse_gitmodules(None) == []


def test_minimum_single_char_path():
    c = classify_subtree("a")
    assert isinstance(c, SubtreeClassification)
    assert c.kind == SOURCE


def test_empty_submodule_list_does_not_raise():
    c = classify_subtree("src/a.cpp", submodule_paths=[])
    assert c.kind == SOURCE


def test_empty_content_stays_source():
    c = classify_subtree("src/a.cpp", content="")
    assert c.kind == SOURCE


def test_empty_sibling_names_stays_source():
    c = classify_subtree("src/config.h", sibling_names=[])
    assert c.kind == SOURCE


def test_persist_empty_iterable_returns_zero():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    assert persist_classification(db, []) == 0


def test_load_from_fresh_db_returns_none():
    db = Path(tempfile.mkdtemp()) / "survey.db"
    assert load_classification(db, "any.cpp", "sha") is None


def test_single_vendored_path_minimum():
    result = classify_subtrees(["vendor/x.c"])
    assert len(result) == 1
    assert result[0].kind == VENDORED

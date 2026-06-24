"""Tests for resolve_target returning 'in_spec'."""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.spec_quality.integration_reachability import resolve_target


def _make_feature(name: str, *acs: str) -> dict:
    return {"name": name, "acceptance_criteria": list(acs)}


def test_module_declared_in_sibling_feature(tmp_path):
    features = [
        _make_feature("F1", "integration: myapp.new_module"),
        _make_feature("F2", "integration: myapp.new_module"),
    ]
    # F1 is in spec because F2 declares the same target
    assert resolve_target("myapp.new_module", features=features, workspace=tmp_path) == "in_spec"


def test_module_in_spec_not_workspace(tmp_path):
    features = [
        _make_feature("F1", "integration: newapp.core"),
        _make_feature("F2", "File exists: src/other.py"),
        _make_feature("F3", "integration: newapp.core"),
    ]
    assert resolve_target("newapp.core", features=features, workspace=tmp_path) == "in_spec"


def test_no_features_list_is_unreachable(tmp_path):
    # With no features, no spec modules exist — must be unreachable
    assert resolve_target("solo.module", features=[], workspace=tmp_path) == "unreachable"


def test_module_in_spec_takes_precedence_before_unreachable(tmp_path):
    features = [
        _make_feature("F1", "integration: future.mod"),
        _make_feature("F2", "integration: future.mod"),
    ]
    result = resolve_target("future.mod", features=features, workspace=tmp_path)
    assert result == "in_spec"

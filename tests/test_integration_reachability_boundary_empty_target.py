"""Boundary test: resolve_target('') returns 'unreachable' (empty edge case)."""
from __future__ import annotations

from bob3.spec_quality.integration_reachability import resolve_target


def test_empty_string_is_unreachable():
    assert resolve_target("") == "unreachable"


def test_whitespace_only_string_is_unreachable():
    assert resolve_target("   ") == "unreachable"


def test_empty_string_with_workspace(tmp_path):
    assert resolve_target("", workspace=tmp_path) == "unreachable"


def test_empty_string_with_features_is_unreachable(tmp_path):
    features = [{"name": "F1", "acceptance_criteria": ["integration: some.module"]}]
    assert resolve_target("", features=features, workspace=tmp_path) == "unreachable"

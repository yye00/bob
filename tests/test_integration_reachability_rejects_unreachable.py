"""Tests for resolve_target returning 'unreachable' and raises_on_unreachable."""
from __future__ import annotations

from pathlib import Path

import pytest

from bob3.spec_quality.integration_reachability import (
    UnreachableIntegrationError,
    raises_on_unreachable,
    resolve_target,
)


def test_nonexistent_module_is_unreachable(tmp_path):
    assert resolve_target("totally.nonexistent.xyz", workspace=tmp_path) == "unreachable"


def test_unreachable_with_no_features(tmp_path):
    assert resolve_target("ghost.module", features=[], workspace=tmp_path) == "unreachable"


def test_unreachable_with_no_sibling_match(tmp_path):
    features = [{"name": "F1", "acceptance_criteria": ["File exists: src/foo.py"]}]
    assert resolve_target("not.in.spec", features=features, workspace=tmp_path) == "unreachable"


def test_raises_on_unreachable_raises_error(tmp_path):
    with pytest.raises(UnreachableIntegrationError) as exc_info:
        raises_on_unreachable("totally.absent.mod", workspace=tmp_path)
    assert "totally.absent.mod" in str(exc_info.value)


def test_raises_on_unreachable_error_has_missing_module(tmp_path):
    with pytest.raises(UnreachableIntegrationError) as exc_info:
        raises_on_unreachable("my.missing.mod", workspace=tmp_path)
    assert exc_info.value.missing_module == "my.missing.mod"


def test_raises_on_unreachable_does_not_raise_for_importable(tmp_path):
    # "os" is always importable — should NOT raise
    raises_on_unreachable("os", workspace=tmp_path)  # no exception


def test_raises_on_unreachable_does_not_raise_for_workspace_file(tmp_path):
    (tmp_path / "src" / "mypkg").mkdir(parents=True)
    (tmp_path / "src" / "mypkg" / "tool.py").write_text("")
    raises_on_unreachable("mypkg.tool", workspace=tmp_path)  # no exception


def test_unreachable_integration_error_str_contains_module():
    err = UnreachableIntegrationError("foo.bar")
    assert "foo.bar" in str(err)


def test_unreachable_integration_error_with_suggestion():
    err = UnreachableIntegrationError("foo.bar", closest_match="foo.baz")
    assert "foo.baz" in str(err)
    assert err.closest_match == "foo.baz"


def test_unreachable_integration_error_with_feature_name():
    err = UnreachableIntegrationError("foo.bar", feature_name="MyFeature")
    assert "MyFeature" in str(err)
    assert err.feature_name == "MyFeature"

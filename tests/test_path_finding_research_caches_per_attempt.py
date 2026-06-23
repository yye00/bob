"""Tests for cache_strategies_per_attempt writing runs/<feature>/research/attempt_<n>.yaml."""

import pathlib
import tempfile

import pytest
import yaml

from bob3.orchestrator.path_finding_retry import (
    FailureClass,
    Strategy,
    cache_strategies_per_attempt,
)


def test_cache_creates_yaml_file(tmp_path):
    feature_id = "test-feature-abc123"
    strategies = [
        Strategy(
            title="Test strategy",
            description="A test strategy",
            failure_class=FailureClass.ambiguous_ac,
        )
    ]
    out_path = cache_strategies_per_attempt(feature_id, 1, strategies, workspace=tmp_path)

    assert out_path.exists(), f"Expected YAML file at {out_path}"
    assert out_path.name == "attempt_1.yaml"


def test_cache_path_structure(tmp_path):
    feature_id = "feat-xyz-789"
    strategies = []
    out_path = cache_strategies_per_attempt(feature_id, 3, strategies, workspace=tmp_path)

    expected = tmp_path / "runs" / feature_id / "research" / "attempt_3.yaml"
    assert out_path == expected


def test_cache_yaml_content(tmp_path):
    feature_id = "feature-content-test"
    strategies = [
        Strategy(
            title="Strategy Alpha",
            description="Alpha description",
            failure_class=FailureClass.import_error,
            priority=1,
        )
    ]
    out_path = cache_strategies_per_attempt(feature_id, 2, strategies, workspace=tmp_path)

    data = yaml.safe_load(out_path.read_text())
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["title"] == "Strategy Alpha"
    assert data[0]["description"] == "Alpha description"
    assert data[0]["failure_class"] == "import_error"
    assert data[0]["priority"] == 1


def test_cache_empty_strategies(tmp_path):
    feature_id = "feature-empty"
    out_path = cache_strategies_per_attempt(feature_id, 1, [], workspace=tmp_path)
    data = yaml.safe_load(out_path.read_text())
    assert data == [] or data is None  # empty list may YAML-dump as []


def test_cache_multiple_strategies(tmp_path):
    feature_id = "feature-multi"
    strategies = [
        Strategy(title="S1", description="D1", failure_class=FailureClass.type_mismatch, priority=1),
        Strategy(title="S2", description="D2", failure_class=FailureClass.type_mismatch, priority=2),
    ]
    out_path = cache_strategies_per_attempt(feature_id, 1, strategies, workspace=tmp_path)
    data = yaml.safe_load(out_path.read_text())
    assert len(data) == 2
    assert data[0]["title"] == "S1"
    assert data[1]["title"] == "S2"


def test_cache_different_attempts_separate_files(tmp_path):
    feature_id = "feature-attempts"
    strategies = [Strategy(title="S", description="D", failure_class=FailureClass.empty_impl)]
    path1 = cache_strategies_per_attempt(feature_id, 1, strategies, workspace=tmp_path)
    path2 = cache_strategies_per_attempt(feature_id, 2, strategies, workspace=tmp_path)

    assert path1 != path2
    assert path1.name == "attempt_1.yaml"
    assert path2.name == "attempt_2.yaml"


def test_cache_creates_parent_dirs(tmp_path):
    feature_id = "some-new-feature"
    strategies = []
    out_path = cache_strategies_per_attempt(feature_id, 1, strategies, workspace=tmp_path)
    assert out_path.parent.exists()

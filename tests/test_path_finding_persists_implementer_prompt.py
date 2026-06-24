"""Tests for persist_implementer_prompt writing runs/<feature>/attempts/<n>/implementer_prompt.txt."""

import pathlib

import pytest

from bob3.orchestrator.path_finding_retry import (
    FailureClass,
    Strategy,
    inject_into_implementer_prompt,
    persist_implementer_prompt,
)


def test_persist_creates_file(tmp_path):
    feature_id = "test-feature-001"
    prompt = "This is the implementer prompt."
    out_path = persist_implementer_prompt(feature_id, 1, prompt, workspace=tmp_path)
    assert out_path.exists(), f"Expected implementer_prompt.txt at {out_path}"


def test_persist_file_name(tmp_path):
    feature_id = "test-feature-002"
    prompt = "Implementer prompt."
    out_path = persist_implementer_prompt(feature_id, 1, prompt, workspace=tmp_path)
    assert out_path.name == "implementer_prompt.txt"


def test_persist_path_structure(tmp_path):
    feature_id = "feat-abc"
    prompt = "Prompt text."
    out_path = persist_implementer_prompt(feature_id, 3, prompt, workspace=tmp_path)
    expected = tmp_path / "runs" / feature_id / "attempts" / "3" / "implementer_prompt.txt"
    assert out_path == expected


def test_persist_file_contains_prompt(tmp_path):
    feature_id = "feat-content"
    prompt = "Implement the frobnication module."
    out_path = persist_implementer_prompt(feature_id, 2, prompt, workspace=tmp_path)
    assert out_path.read_text() == prompt


def test_persist_creates_parent_directories(tmp_path):
    feature_id = "feat-new-dirs"
    prompt = "Some prompt."
    out_path = persist_implementer_prompt(feature_id, 1, prompt, workspace=tmp_path)
    assert out_path.parent.exists()


def test_persist_different_attempts_different_files(tmp_path):
    feature_id = "feat-attempts"
    path1 = persist_implementer_prompt(feature_id, 1, "Prompt 1", workspace=tmp_path)
    path2 = persist_implementer_prompt(feature_id, 2, "Prompt 2", workspace=tmp_path)
    assert path1 != path2
    assert path1.read_text() == "Prompt 1"
    assert path2.read_text() == "Prompt 2"


def test_persist_injected_prompt_round_trips(tmp_path):
    feature_id = "feat-roundtrip"
    strategies = [
        Strategy(
            title="Use TDD",
            description="Write tests first",
            failure_class=FailureClass.ambiguous_ac,
        )
    ]
    base = "Base implementer prompt."
    injected = inject_into_implementer_prompt(base, strategies, FailureClass.ambiguous_ac, attempt_number=2)
    out_path = persist_implementer_prompt(feature_id, 2, injected, workspace=tmp_path)

    persisted_text = out_path.read_text()
    assert "Research-Augmented Retry" in persisted_text
    assert base in persisted_text


def test_persist_returns_path_object(tmp_path):
    feature_id = "feat-return-type"
    out_path = persist_implementer_prompt(feature_id, 1, "prompt", workspace=tmp_path)
    assert isinstance(out_path, pathlib.Path)

"""Tests for bob.worker_leverage.

Feature 79ba244c: Claude-Code worker leverage — enable prompt cache, slim
per-worker context, re-declare settings.

ACs tested:
  - Function defined: bob.worker_leverage.enable_prompt_caching
  - Function defined: bob.worker_leverage.generate_worker_md
  - Function defined: bob.worker_leverage.write_worker_settings
  - integration: bob.dispatch
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bob import worker_leverage


def _make_feature(
    *,
    id: str = "feat-001",
    name: str = "Test Feature",
    description: str = "A test feature",
    acceptance_criteria: str | None = '["File exists: foo.py"]',
    localization_shortlist: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        localization_shortlist=localization_shortlist or ["src/foo.py"],
    )


# ── Function existence (ACs) ──────────────────────────────────────────────────

def test_enable_prompt_caching_defined():
    assert callable(worker_leverage.enable_prompt_caching)


def test_generate_worker_md_defined():
    assert callable(worker_leverage.generate_worker_md)


def test_write_worker_settings_defined():
    assert callable(worker_leverage.write_worker_settings)


# ── enable_prompt_caching ─────────────────────────────────────────────────────

class TestEnablePromptCaching:
    def test_returns_dict_with_cache_flag(self):
        env = worker_leverage.enable_prompt_caching()
        assert env["ANTHROPIC_PROMPT_CACHING"] == "1"

    def test_merges_existing_env(self):
        env = worker_leverage.enable_prompt_caching({"FOO": "bar"})
        assert env["FOO"] == "bar"
        assert env["ANTHROPIC_PROMPT_CACHING"] == "1"

    def test_does_not_mutate_input(self):
        original = {"FOO": "bar"}
        worker_leverage.enable_prompt_caching(original)
        assert "ANTHROPIC_PROMPT_CACHING" not in original

    def test_none_env_returns_dict(self):
        env = worker_leverage.enable_prompt_caching(None)
        assert isinstance(env, dict)

    def test_invalid_env_type_raises(self):
        with pytest.raises(ValueError):
            worker_leverage.enable_prompt_caching("not-a-dict")


# ── generate_worker_md ────────────────────────────────────────────────────────

class TestGenerateWorkerMd:
    def test_contains_feature_name(self):
        md = worker_leverage.generate_worker_md(_make_feature(name="MyFeat"), "/ws")
        assert "MyFeat" in md

    def test_contains_acceptance_criteria_section(self):
        md = worker_leverage.generate_worker_md(_make_feature(), "/ws")
        assert "Acceptance Criteria" in md

    def test_contains_workspace(self):
        md = worker_leverage.generate_worker_md(_make_feature(), "/my/workspace")
        assert "/my/workspace" in md

    def test_contains_localization_shortlist(self):
        md = worker_leverage.generate_worker_md(
            _make_feature(localization_shortlist=["src/bar.py"]), "/ws"
        )
        assert "src/bar.py" in md

    def test_none_acs_returns_string(self):
        md = worker_leverage.generate_worker_md(
            _make_feature(acceptance_criteria=None), "/ws"
        )
        assert isinstance(md, str)

    def test_none_feature_raises(self):
        with pytest.raises(ValueError):
            worker_leverage.generate_worker_md(None, "/ws")


# ── write_worker_settings ─────────────────────────────────────────────────────

class TestWriteWorkerSettings:
    def test_writes_settings_file(self, tmp_path):
        path = worker_leverage.write_worker_settings(_make_feature(), bob_dir=tmp_path)
        assert path.exists()

    def test_settings_have_permissions_allow(self, tmp_path):
        path = worker_leverage.write_worker_settings(_make_feature(), bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "allow" in data["permissions"]

    def test_extra_allow_included(self, tmp_path):
        path = worker_leverage.write_worker_settings(
            _make_feature(), bob_dir=tmp_path, extra_allow=["Bash(pytest*)"]
        )
        data = json.loads(path.read_text())
        assert "Bash(pytest*)" in data["permissions"]["allow"]

    def test_returns_path(self, tmp_path):
        path = worker_leverage.write_worker_settings(_make_feature(), bob_dir=tmp_path)
        assert isinstance(path, Path)

    def test_none_feature_raises(self, tmp_path):
        with pytest.raises(ValueError):
            worker_leverage.write_worker_settings(None, bob_dir=tmp_path)


# ── Integration: bob.dispatch ─────────────────────────────────────────────────

class TestDispatchIntegration:
    def test_enable_prompt_caching_matches_dispatch(self):
        from bob import dispatch

        assert (
            worker_leverage.enable_prompt_caching()["ANTHROPIC_PROMPT_CACHING"]
            == dispatch.enable_worker_prompt_cache()["ANTHROPIC_PROMPT_CACHING"]
        )

    def test_generate_worker_md_matches_dispatch(self):
        from bob import dispatch

        feature = _make_feature()
        assert worker_leverage.generate_worker_md(
            feature, "/ws"
        ) == dispatch.build_worker_md(feature, "/ws")

    def test_write_worker_settings_matches_dispatch(self, tmp_path):
        from bob import dispatch

        feature = _make_feature(id="feat-integ")
        p1 = worker_leverage.write_worker_settings(feature, bob_dir=tmp_path / "a")
        p2 = dispatch.write_feature_settings(feature, bob_dir=tmp_path / "b")
        assert json.loads(p1.read_text()) == json.loads(p2.read_text())

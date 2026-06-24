"""Tests for per-worker settings isolation in bob.dispatch.

AC: pytest: tests/test_worker_settings_isolation.py

Verifies that workers receive isolated settings.json files written per-feature,
preventing permission-prompt stalls from the lack of parent settings inheritance
(Claude Code issue #27661).

Functions under test: write_feature_settings, generate_worker_settings,
enable_worker_prompt_cache.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bob.dispatch import (
    enable_worker_prompt_cache,
    generate_worker_settings,
    write_feature_settings,
)


def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-isolation-01",
        name="Isolation Feature",
        description="Test feature for isolation",
        acceptance_criteria='["File exists: foo.py"]',
        localization_shortlist=[],
        skip_repo_tree=False,
        skip_repro_test=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestWriteFeatureSettingsIsolation:
    """Tests that each feature gets its own isolated settings file."""

    def test_settings_written_to_feature_specific_dir(self, tmp_path):
        feature = _make_feature(id="feat-iso-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert path.parent.name == "feat-iso-01"

    def test_settings_file_named_settings_json(self, tmp_path):
        feature = _make_feature(id="feat-iso-02")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert path.name == "settings.json"

    def test_settings_path_under_bob_features_dir(self, tmp_path):
        feature = _make_feature(id="feat-iso-03")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert (tmp_path / "features" / "feat-iso-03" / "settings.json") == path

    def test_two_features_get_separate_settings_files(self, tmp_path):
        feat_a = _make_feature(id="feat-iso-a")
        feat_b = _make_feature(id="feat-iso-b")
        path_a = write_feature_settings(feat_a, bob_dir=tmp_path)
        path_b = write_feature_settings(feat_b, bob_dir=tmp_path)
        assert path_a != path_b
        assert path_a.exists()
        assert path_b.exists()

    def test_extra_allow_isolated_to_feature(self, tmp_path):
        """Extra allow rules written for one feature do not appear in another's settings."""
        feat_a = _make_feature(id="feat-iso-extra-a")
        feat_b = _make_feature(id="feat-iso-extra-b")
        write_feature_settings(feat_a, bob_dir=tmp_path, extra_allow=["Bash(special-cmd*)"])
        write_feature_settings(feat_b, bob_dir=tmp_path)

        data_a = json.loads((tmp_path / "features" / "feat-iso-extra-a" / "settings.json").read_text())
        data_b = json.loads((tmp_path / "features" / "feat-iso-extra-b" / "settings.json").read_text())

        assert "Bash(special-cmd*)" in data_a["permissions"]["allow"]
        assert "Bash(special-cmd*)" not in data_b["permissions"]["allow"]

    def test_settings_file_is_valid_json(self, tmp_path):
        feature = _make_feature(id="feat-iso-json")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert isinstance(data, dict)

    def test_settings_has_permissions_key(self, tmp_path):
        feature = _make_feature(id="feat-iso-perms")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "permissions" in data

    def test_settings_permissions_has_allow(self, tmp_path):
        feature = _make_feature(id="feat-iso-allow")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "allow" in data["permissions"]

    def test_settings_permissions_has_deny(self, tmp_path):
        feature = _make_feature(id="feat-iso-deny")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "deny" in data["permissions"]

    def test_default_allow_includes_python(self, tmp_path):
        feature = _make_feature(id="feat-iso-py")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("python" in a.lower() for a in allow)

    def test_default_allow_includes_pytest(self, tmp_path):
        feature = _make_feature(id="feat-iso-pt")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("pytest" in a.lower() for a in allow)

    def test_default_allow_includes_read(self, tmp_path):
        feature = _make_feature(id="feat-iso-rd")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("Read" in a for a in allow)

    def test_default_allow_includes_write(self, tmp_path):
        feature = _make_feature(id="feat-iso-wr")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("Write" in a for a in allow)

    def test_overwrite_existing_settings(self, tmp_path):
        """Writing settings twice updates the file rather than failing."""
        feature = _make_feature(id="feat-iso-overwrite")
        path1 = write_feature_settings(feature, bob_dir=tmp_path)
        path2 = write_feature_settings(
            feature, bob_dir=tmp_path, extra_allow=["Bash(new-tool*)"]
        )
        assert path1 == path2
        data = json.loads(path2.read_text())
        assert "Bash(new-tool*)" in data["permissions"]["allow"]

    def test_creates_parent_directories(self, tmp_path):
        """bob_dir does not need to pre-exist."""
        deep_bob_dir = tmp_path / "nested" / "deep" / ".bob"
        feature = _make_feature(id="feat-iso-deep")
        path = write_feature_settings(feature, bob_dir=deep_bob_dir)
        assert path.exists()


class TestGenerateWorkerSettingsAlias:
    """Verify generate_worker_settings delegates to write_feature_settings correctly."""

    def test_returns_path(self, tmp_path):
        feature = _make_feature(id="feat-gen-01")
        result = generate_worker_settings(feature, bob_dir=tmp_path)
        assert isinstance(result, Path)

    def test_file_exists(self, tmp_path):
        feature = _make_feature(id="feat-gen-02")
        path = generate_worker_settings(feature, bob_dir=tmp_path)
        assert path.exists()

    def test_same_path_as_write_feature_settings(self, tmp_path):
        feature = _make_feature(id="feat-gen-same")
        path_gen = generate_worker_settings(feature, bob_dir=tmp_path / "gen")
        path_write = write_feature_settings(feature, bob_dir=tmp_path / "write")
        assert path_gen.name == path_write.name
        assert path_gen.parent.name == path_write.parent.name

    def test_extra_allow_passed_through(self, tmp_path):
        feature = _make_feature(id="feat-gen-extra")
        path = generate_worker_settings(
            feature, bob_dir=tmp_path, extra_allow=["Bash(custom*)"]
        )
        data = json.loads(path.read_text())
        assert "Bash(custom*)" in data["permissions"]["allow"]

    def test_produces_valid_json(self, tmp_path):
        feature = _make_feature(id="feat-gen-json")
        path = generate_worker_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert isinstance(data, dict)

    def test_feature_id_in_path(self, tmp_path):
        feature = _make_feature(id="feat-gen-id-check")
        path = generate_worker_settings(feature, bob_dir=tmp_path)
        assert "feat-gen-id-check" in str(path)


class TestEnableWorkerPromptCacheIsolation:
    """Verify prompt-cache env setting is correctly applied to each worker env."""

    def test_sets_anthropic_prompt_caching_to_1(self):
        env = enable_worker_prompt_cache()
        assert env.get("ANTHROPIC_PROMPT_CACHING") == "1"

    def test_merges_with_existing_env(self):
        existing = {"MY_VAR": "hello", "OTHER": "world"}
        result = enable_worker_prompt_cache(existing)
        assert result["MY_VAR"] == "hello"
        assert result["ANTHROPIC_PROMPT_CACHING"] == "1"

    def test_does_not_mutate_input_env(self):
        original = {"EXISTING": "value"}
        original_copy = dict(original)
        enable_worker_prompt_cache(original)
        assert original == original_copy

    def test_none_input_returns_cache_env(self):
        result = enable_worker_prompt_cache(None)
        assert result["ANTHROPIC_PROMPT_CACHING"] == "1"

    def test_empty_input_returns_cache_env(self):
        result = enable_worker_prompt_cache({})
        assert result["ANTHROPIC_PROMPT_CACHING"] == "1"

    def test_two_workers_get_independent_envs(self):
        env_a = enable_worker_prompt_cache({"WORKER_ID": "A"})
        env_b = enable_worker_prompt_cache({"WORKER_ID": "B"})
        assert env_a["WORKER_ID"] == "A"
        assert env_b["WORKER_ID"] == "B"
        assert env_a["ANTHROPIC_PROMPT_CACHING"] == "1"
        assert env_b["ANTHROPIC_PROMPT_CACHING"] == "1"

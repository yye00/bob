"""Boundary tests for bob3.dispatch worker-leverage functions.

AC: boundary case — empty, zero, or minimum input returns a well-defined result
rather than raising (boundary case).

Functions under test: emit_worker_cache_event, build_worker_md,
write_feature_settings, spawn_worker.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from bob3.dispatch import (
    build_worker_md,
    emit_worker_cache_event,
    spawn_worker,
    write_feature_settings,
)


def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-boundary-01",
        name="Boundary Feature",
        description="",
        acceptance_criteria=None,
        localization_shortlist=[],
        skip_repo_tree=False,
        skip_repro_test=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestEmitWorkerCacheEventBoundary:
    def test_zero_cache_read_and_write(self):
        result = emit_worker_cache_event(0, 0)
        assert result["cache_read"] == 0
        assert result["cache_write"] == 0
        assert result["event"] == "WORKER_CACHE_HIT"

    def test_very_large_values(self):
        result = emit_worker_cache_event(10**9, 10**9)
        assert result["cache_read"] == 10**9
        assert result["cache_write"] == 10**9

    def test_no_feature_id_is_fine(self):
        result = emit_worker_cache_event(0, 0)
        assert "feature_id" not in result

    def test_empty_string_feature_id(self):
        result = emit_worker_cache_event(0, 0, feature_id="")
        assert result["feature_id"] == ""


class TestBuildWorkerMdBoundary:
    def test_empty_name_returns_string(self):
        feature = _make_feature(name="")
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)

    def test_empty_description_returns_string(self):
        feature = _make_feature(description="")
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)

    def test_none_acceptance_criteria_returns_string(self):
        feature = _make_feature(acceptance_criteria=None)
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)
        assert "Acceptance Criteria" in result

    def test_empty_list_acceptance_criteria(self):
        feature = _make_feature(acceptance_criteria="[]")
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)

    def test_empty_localization_shortlist(self):
        feature = _make_feature(localization_shortlist=[])
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)

    def test_workspace_empty_string(self):
        feature = _make_feature()
        result = build_worker_md(feature, "")
        assert isinstance(result, str)

    def test_single_ac(self):
        feature = _make_feature(acceptance_criteria='["File exists: foo.py"]')
        result = build_worker_md(feature, "/workspace")
        assert "foo.py" in result


class TestWriteFeatureSettingsBoundary:
    def test_no_extra_allow_returns_path(self, tmp_path):
        feature = _make_feature(id="feat-boundary-s1")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        assert isinstance(path, Path)
        assert path.exists()

    def test_empty_extra_allow(self, tmp_path):
        feature = _make_feature(id="feat-boundary-s2")
        path = write_feature_settings(feature, bob3_dir=tmp_path, extra_allow=[])
        data = json.loads(path.read_text())
        assert "allow" in data["permissions"]

    def test_single_extra_allow(self, tmp_path):
        feature = _make_feature(id="feat-boundary-s3")
        path = write_feature_settings(feature, bob3_dir=tmp_path, extra_allow=["Read(*)"])
        data = json.loads(path.read_text())
        assert "Read(*)" in data["permissions"]["allow"]

    def test_minimum_feature_id(self, tmp_path):
        feature = _make_feature(id="x")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        assert path.exists()


class TestSpawnWorkerBoundary:
    def test_empty_prompt_does_not_raise(self, tmp_path):
        feature = _make_feature(id="feat-boundary-sp1")
        captured = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured["env"] = env
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob3.dispatch.subprocess.run", side_effect=fake_run):
            result = spawn_worker(
                feature, "", tmp_path, bob3_dir=tmp_path / ".bob3"
            )
        assert result["returncode"] == 0

    def test_minimum_timeout_does_not_raise(self, tmp_path):
        feature = _make_feature(id="feat-boundary-sp2")

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob3.dispatch.subprocess.run", side_effect=fake_run):
            result = spawn_worker(
                feature, "prompt", tmp_path, bob3_dir=tmp_path / ".bob3", timeout=1
            )
        assert result["returncode"] == 0

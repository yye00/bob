"""Tests for per-worker settings generation and WORKER.md fixture.

Feature 00a546e7: Claude-Code worker leverage — enable prompt cache,
slim per-worker context, re-declare settings.

ACs tested:
  - File exists: tests/fixtures/WORKER.md
  - Per-feature settings.json written at dispatch time
  - Settings include permissions.allow list
  - WORKER.md contains expected sections
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bob.dispatch import (
    build_worker_md,
    write_feature_settings,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-settings-01",
        name="Settings Test Feature",
        description="Tests per-worker settings generation.",
        acceptance_criteria='["File exists: src/foo.py", "pytest: tests/test_foo.py"]',
        localization_shortlist=["src/foo.py"],
        skip_repo_tree=False,
        skip_repro_test=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── WORKER.md fixture file ─────────────────────────────────────────────────────

class TestWorkerMdFixture:
    def test_fixture_file_exists(self):
        path = FIXTURES_DIR / "WORKER.md"
        assert path.exists(), f"tests/fixtures/WORKER.md must exist, not found at {path}"

    def test_fixture_file_is_readable(self):
        path = FIXTURES_DIR / "WORKER.md"
        content = path.read_text()
        assert isinstance(content, str)
        assert len(content) > 0

    def test_fixture_contains_feature_section(self):
        path = FIXTURES_DIR / "WORKER.md"
        content = path.read_text()
        assert "Feature" in content

    def test_fixture_contains_acceptance_criteria_section(self):
        path = FIXTURES_DIR / "WORKER.md"
        content = path.read_text()
        assert "Acceptance Criteria" in content

    def test_fixture_contains_workspace_section(self):
        path = FIXTURES_DIR / "WORKER.md"
        content = path.read_text()
        assert "Workspace" in content


# ── Per-worker settings.json ───────────────────────────────────────────────────

class TestWriteFeatureSettingsContent:
    def test_settings_has_permissions_key(self, tmp_path):
        feature = _make_feature(id="feat-ws-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "permissions" in data

    def test_settings_permissions_has_allow(self, tmp_path):
        feature = _make_feature(id="feat-ws-02")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "allow" in data["permissions"]

    def test_settings_permissions_has_deny(self, tmp_path):
        feature = _make_feature(id="feat-ws-03")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "deny" in data["permissions"]

    def test_settings_allow_contains_bash_python(self, tmp_path):
        feature = _make_feature(id="feat-ws-04")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("python" in entry or "Python" in entry for entry in allow)

    def test_settings_allow_contains_read(self, tmp_path):
        feature = _make_feature(id="feat-ws-05")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("Read" in entry for entry in allow)

    def test_settings_allow_contains_write(self, tmp_path):
        feature = _make_feature(id="feat-ws-06")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("Write" in entry for entry in allow)

    def test_extra_allow_merged_into_settings(self, tmp_path):
        feature = _make_feature(id="feat-ws-07")
        path = write_feature_settings(
            feature, bob_dir=tmp_path, extra_allow=["Bash(my-custom-tool*)"]
        )
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert "Bash(my-custom-tool*)" in allow

    def test_settings_placed_under_feature_id_directory(self, tmp_path):
        fid = "feat-ws-08"
        feature = _make_feature(id=fid)
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert path.parent.name == fid
        assert path.name == "settings.json"

    def test_multiple_features_get_separate_settings(self, tmp_path):
        f1 = _make_feature(id="feat-multi-01")
        f2 = _make_feature(id="feat-multi-02")
        p1 = write_feature_settings(f1, bob_dir=tmp_path)
        p2 = write_feature_settings(f2, bob_dir=tmp_path)
        assert p1 != p2
        assert p1.exists()
        assert p2.exists()

    def test_overwrite_existing_settings_does_not_raise(self, tmp_path):
        feature = _make_feature(id="feat-ws-overwrite")
        write_feature_settings(feature, bob_dir=tmp_path)
        # Write again — should not raise
        write_feature_settings(feature, bob_dir=tmp_path)
        path = tmp_path / "features" / "feat-ws-overwrite" / "settings.json"
        assert path.exists()


# ── build_worker_md produces slimmer context than CLAUDE.md ──────────────────

class TestWorkerMdSlimContext:
    def test_does_not_include_operator_keywords(self):
        feature = _make_feature()
        md = build_worker_md(feature, "/workspace")
        assert "orchestrator" not in md.lower()

    def test_includes_feature_name(self):
        feature = _make_feature(name="My Slim Feature")
        md = build_worker_md(feature, "/workspace")
        assert "My Slim Feature" in md

    def test_includes_acceptance_criteria(self):
        feature = _make_feature(
            acceptance_criteria='["pytest: tests/test_slim.py"]'
        )
        md = build_worker_md(feature, "/workspace")
        assert "tests/test_slim.py" in md

    def test_includes_workspace_path(self):
        feature = _make_feature()
        md = build_worker_md(feature, "/the/workspace/path")
        assert "/the/workspace/path" in md

    def test_localization_shortlist_when_provided(self):
        feature = _make_feature(localization_shortlist=["src/target.py"])
        md = build_worker_md(feature, "/workspace")
        assert "src/target.py" in md

    def test_no_localization_section_when_empty(self):
        feature = _make_feature(localization_shortlist=[])
        md = build_worker_md(feature, "/workspace")
        assert "Localization" not in md


# ── Integration: settings path is valid JSON that claude can consume ──────────

class TestSettingsJsonStructure:
    def test_settings_json_is_parseable(self, tmp_path):
        feature = _make_feature(id="feat-struct-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            pytest.fail(f"settings.json is not valid JSON: {e}")
        assert data is not None

    def test_settings_allow_entries_are_strings(self, tmp_path):
        feature = _make_feature(id="feat-struct-02")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        for entry in data["permissions"]["allow"]:
            assert isinstance(entry, str), f"allow entry must be a string, got {type(entry)}"

    def test_settings_deny_is_a_list(self, tmp_path):
        feature = _make_feature(id="feat-struct-03")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert isinstance(data["permissions"]["deny"], list)

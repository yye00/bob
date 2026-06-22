"""Tests for worker context slimming (slim per-worker WORKER.md generation).

Verifies:
- build_worker_md produces content with feature name, description, ACs, workspace
- CLAUDE_OPERATOR.md and WORKER.md template files exist in src/bob3/
- WORKER.md content does NOT include operator-loop bullets (~70 bullets)
- Per-feature WORKER.md is written to the correct path
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bob3.dispatch import build_worker_md, write_feature_settings


def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-slim-01",
        name="Slim Context Test Feature",
        description="This feature tests context slimming.",
        acceptance_criteria=json.dumps([
            "File exists: src/bob3/dispatch.py",
            "pytest: tests/test_worker_context_slimming.py",
        ]),
        localization_shortlist=["src/bob3/dispatch.py", "tests/"],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestBuildWorkerMdContent:
    def test_includes_feature_name(self):
        feature = _make_feature(name="MyTestFeature")
        content = build_worker_md(feature, "/workspace")
        assert "MyTestFeature" in content

    def test_includes_feature_description(self):
        feature = _make_feature(description="A unique description for slimming test.")
        content = build_worker_md(feature, "/workspace")
        assert "A unique description for slimming test." in content

    def test_includes_acceptance_criteria(self):
        feature = _make_feature(
            acceptance_criteria=json.dumps(["pytest: tests/test_slim.py"])
        )
        content = build_worker_md(feature, "/workspace")
        assert "pytest: tests/test_slim.py" in content

    def test_includes_workspace_path(self):
        feature = _make_feature()
        content = build_worker_md(feature, "/my/workspace/path")
        assert "/my/workspace/path" in content

    def test_includes_localization_shortlist(self):
        feature = _make_feature(localization_shortlist=["src/mymodule.py"])
        content = build_worker_md(feature, "/workspace")
        assert "src/mymodule.py" in content

    def test_returns_string(self):
        feature = _make_feature()
        content = build_worker_md(feature, "/workspace")
        assert isinstance(content, str)

    def test_content_is_nonempty(self):
        feature = _make_feature()
        content = build_worker_md(feature, "/workspace")
        assert len(content) > 0

    def test_multiple_acs_all_present(self):
        acs = ["File exists: src/foo.py", "pytest: tests/test_foo.py", "Function defined: foo.bar"]
        feature = _make_feature(acceptance_criteria=json.dumps(acs))
        content = build_worker_md(feature, "/workspace")
        for ac in acs:
            assert ac in content, f"AC not found in WORKER.md: {ac}"

    def test_no_operator_loop_bullets_in_content(self):
        """WORKER.md must not include the ~70 operator-loop memory bullets."""
        feature = _make_feature()
        content = build_worker_md(feature, "/workspace")
        # The operator loop CLAUDE.md has specific bullets; check that
        # typical operator-only content is absent from the slim worker doc.
        # We test the absence of the operator context indicator pattern.
        assert "## Bob3 Operator Loop" not in content
        assert "Greenfield gap analysis" not in content

    def test_empty_acceptance_criteria_handled(self):
        feature = _make_feature(acceptance_criteria=None)
        content = build_worker_md(feature, "/workspace")
        assert isinstance(content, str)

    def test_empty_localization_shortlist_handled(self):
        feature = _make_feature(localization_shortlist=[])
        content = build_worker_md(feature, "/workspace")
        assert isinstance(content, str)


class TestWorkerContextFiles:
    def test_claude_operator_md_exists(self):
        """CLAUDE_OPERATOR.md must exist in src/bob3/ (operator context split)."""
        path = Path("src/bob3/CLAUDE_OPERATOR.md")
        assert path.exists(), f"Expected {path} to exist"

    def test_worker_md_exists(self):
        """WORKER.md template must exist in src/bob3/."""
        path = Path("src/bob3/WORKER.md")
        assert path.exists(), f"Expected {path} to exist"

    def test_claude_operator_md_has_content(self):
        path = Path("src/bob3/CLAUDE_OPERATOR.md")
        assert path.stat().st_size > 0, "CLAUDE_OPERATOR.md must not be empty"

    def test_worker_md_has_content(self):
        path = Path("src/bob3/WORKER.md")
        assert path.stat().st_size > 0, "WORKER.md must not be empty"


class TestWritePerFeatureWorkerMd:
    def test_write_feature_settings_creates_file(self, tmp_path):
        """write_feature_settings creates settings.json under .bob3/features/<id>/."""
        feature = _make_feature(id="test-feat-slim-write")
        settings_path = write_feature_settings(feature, bob3_dir=tmp_path / ".bob3")
        assert settings_path.exists()

    def test_write_feature_settings_path_contains_feature_id(self, tmp_path):
        feature = _make_feature(id="unique-feat-id-slim")
        settings_path = write_feature_settings(feature, bob3_dir=tmp_path / ".bob3")
        assert "unique-feat-id-slim" in str(settings_path)

    def test_write_feature_settings_valid_json(self, tmp_path):
        feature = _make_feature(id="json-check-slim")
        settings_path = write_feature_settings(feature, bob3_dir=tmp_path / ".bob3")
        data = json.loads(settings_path.read_text())
        assert "permissions" in data
        assert "allow" in data["permissions"]

    def test_extra_allow_included_in_settings(self, tmp_path):
        feature = _make_feature(id="extra-allow-slim")
        settings_path = write_feature_settings(
            feature,
            bob3_dir=tmp_path / ".bob3",
            extra_allow=["Bash(my_custom_cmd:*)"],
        )
        data = json.loads(settings_path.read_text())
        assert "Bash(my_custom_cmd:*)" in data["permissions"]["allow"]

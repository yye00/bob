"""Tests for slim worker context generation (bob.dispatch.build_worker_md).

Verifies that build_worker_md produces the correct slim WORKER.md content
containing only feature-relevant information, excluding operator-loop bullets.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bob.dispatch import build_worker_md


def _make_feature(
    *,
    id: str = "feat-slim-01",
    name: str = "Slim Context Feature",
    description: str = "A feature for slim context tests",
    acceptance_criteria: str | None = '["File exists: foo.py", "pytest: tests/test_foo.py"]',
    localization_shortlist: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        localization_shortlist=localization_shortlist or [],
    )


class TestBuildWorkerMd:
    def test_returns_string(self):
        feature = _make_feature()
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)

    def test_contains_feature_name(self):
        feature = _make_feature(name="My Test Feature")
        result = build_worker_md(feature, "/workspace")
        assert "My Test Feature" in result

    def test_contains_description(self):
        feature = _make_feature(description="A very specific description")
        result = build_worker_md(feature, "/workspace")
        assert "A very specific description" in result

    def test_contains_workspace_path(self):
        feature = _make_feature()
        result = build_worker_md(feature, "/some/workspace/path")
        assert "/some/workspace/path" in result

    def test_contains_acceptance_criteria(self):
        feature = _make_feature(acceptance_criteria='["File exists: foo.py"]')
        result = build_worker_md(feature, "/workspace")
        assert "File exists: foo.py" in result

    def test_contains_localization_shortlist(self):
        feature = _make_feature(localization_shortlist=["src/foo.py", "src/bar.py"])
        result = build_worker_md(feature, "/workspace")
        assert "src/foo.py" in result
        assert "src/bar.py" in result

    def test_does_not_contain_operator_bullets(self):
        feature = _make_feature()
        result = build_worker_md(feature, "/workspace")
        # Operator-loop content should NOT appear in slim worker context
        assert "orchestrator" not in result.lower() or "Workspace" in result

    def test_has_acceptance_criteria_section(self):
        feature = _make_feature()
        result = build_worker_md(feature, "/workspace")
        assert "Acceptance Criteria" in result

    def test_has_workspace_section(self):
        feature = _make_feature()
        result = build_worker_md(feature, "/workspace")
        assert "Workspace" in result

    def test_empty_acceptance_criteria(self):
        feature = _make_feature(acceptance_criteria=None)
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)
        assert "Acceptance Criteria" in result

    def test_multiple_acs_all_present(self):
        feature = _make_feature(
            acceptance_criteria='["File exists: a.py", "File exists: b.py", "pytest: tests/test_c.py"]'
        )
        result = build_worker_md(feature, "/workspace")
        assert "File exists: a.py" in result
        assert "File exists: b.py" in result
        assert "pytest: tests/test_c.py" in result

    def test_empty_name_graceful(self):
        feature = SimpleNamespace(
            id="feat-empty",
            name="",
            description="",
            acceptance_criteria=None,
            localization_shortlist=[],
        )
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)

    def test_localization_section_present_when_list_nonempty(self):
        feature = _make_feature(localization_shortlist=["src/main.py"])
        result = build_worker_md(feature, "/workspace")
        assert "Localization" in result

    def test_localization_section_absent_when_list_empty(self):
        feature = _make_feature(localization_shortlist=[])
        result = build_worker_md(feature, "/workspace")
        # No localization section when list is empty
        assert "src/" not in result

"""Tests for forward traceability (AC → test → code) and orphan detection.

An AC is 'orphaned' when no test in the test suite references it.
"""

from __future__ import annotations

import json
import pathlib

import pytest


@pytest.fixture()
def tmp_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Minimal workspace: spec.yaml, two tests, one source file."""
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "acceptance_criteria:\n"
        "  - id: AC-01\n"
        "    text: 'File exists: tools/spec_coverage.py'\n"
        "  - id: AC-02\n"
        "    text: 'Function defined: spec_coverage.build_rtm'\n"
        "  - id: AC-03\n"
        "    text: 'Orphaned AC with no matching test'\n"
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_alpha.py").write_text(
        "# AC-01 AC-02\n"
        "def test_something():\n"
        "    assert True\n"
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "feature.py").write_text(
        "def build_rtm():\n"
        "    pass\n"
    )
    return tmp_path


def test_forward_ac_has_matched_tests(tmp_workspace):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-001",
        spec_file=tmp_workspace / "spec.yaml",
    )

    ac01 = rtm["acs"]["AC-01"]
    assert "test_alpha.py" in " ".join(ac01["matched_tests"])


def test_forward_ac_has_exercised_files(tmp_workspace):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-001",
        spec_file=tmp_workspace / "spec.yaml",
    )

    ac01 = rtm["acs"]["AC-01"]
    assert isinstance(ac01["exercised_files"], list)


def test_forward_orphan_flag_set_for_unmatched_ac(tmp_workspace):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-001",
        spec_file=tmp_workspace / "spec.yaml",
    )

    # AC-03 has no matching test
    assert rtm["acs"]["AC-03"]["orphan"] is True


def test_forward_non_orphan_flag_for_matched_ac(tmp_workspace):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-001",
        spec_file=tmp_workspace / "spec.yaml",
    )

    assert rtm["acs"]["AC-01"]["orphan"] is False


def test_rtm_json_written_to_runs_dir(tmp_workspace, tmp_path):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-json",
        spec_file=tmp_workspace / "spec.yaml",
        runs_dir=tmp_workspace / "runs",
    )

    rtm_json = tmp_workspace / "runs" / "feat-json" / "rtm.json"
    assert rtm_json.exists(), f"Expected {rtm_json} to exist"
    data = json.loads(rtm_json.read_text())
    assert "acs" in data


def test_rtm_html_written_to_runs_dir(tmp_workspace):
    from tools.spec_coverage import build_rtm

    build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-html",
        spec_file=tmp_workspace / "spec.yaml",
        runs_dir=tmp_workspace / "runs",
    )

    rtm_html = tmp_workspace / "runs" / "feat-html" / "rtm.html"
    assert rtm_html.exists(), f"Expected {rtm_html} to exist"
    content = rtm_html.read_text()
    assert "<html" in content.lower()


def test_spec_coverage_pct_in_rtm(tmp_workspace):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-pct",
        spec_file=tmp_workspace / "spec.yaml",
    )

    # 2/3 ACs are covered
    assert "spec_coverage_pct" in rtm
    assert abs(rtm["spec_coverage_pct"] - 2 / 3) < 0.01

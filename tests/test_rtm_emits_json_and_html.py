"""Tests for emit_rtm_json and emit_rtm_html public API functions."""

from __future__ import annotations

import json
import pathlib

import pytest


@pytest.fixture()
def minimal_rtm() -> dict:
    return {
        "feature_id": "feat-emit-test",
        "acs": {
            "AC-01": {
                "text": "Some AC",
                "matched_tests": ["tests/test_foo.py"],
                "exercised_files": ["tests/test_foo.py"],
                "orphan": False,
            }
        },
        "spec_coverage_pct": 1.0,
        "untraced_implementations": [],
    }


def test_emit_rtm_json_creates_file(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_json

    out_path = emit_rtm_json(minimal_rtm, runs_dir=tmp_path, feature_id="feat-emit-test")

    assert out_path.exists()
    assert out_path.name == "rtm.json"


def test_emit_rtm_json_content_is_valid_json(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_json

    emit_rtm_json(minimal_rtm, runs_dir=tmp_path, feature_id="feat-emit-test")
    data = json.loads((tmp_path / "feat-emit-test" / "rtm.json").read_text())
    assert "acs" in data
    assert data["feature_id"] == "feat-emit-test"


def test_emit_rtm_json_creates_runs_subdir(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_json

    emit_rtm_json(minimal_rtm, runs_dir=tmp_path / "runs", feature_id="feat-sub")

    assert (tmp_path / "runs" / "feat-sub" / "rtm.json").exists()


def test_emit_rtm_html_creates_file(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_html

    out_path = emit_rtm_html(minimal_rtm, runs_dir=tmp_path, feature_id="feat-html-test")

    assert out_path.exists()
    assert out_path.name == "rtm.html"


def test_emit_rtm_html_contains_html_structure(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_html

    emit_rtm_html(minimal_rtm, runs_dir=tmp_path, feature_id="feat-html-test")
    content = (tmp_path / "feat-html-test" / "rtm.html").read_text()

    assert "<!DOCTYPE html>" in content or "<html" in content.lower()
    assert "AC-01" in content


def test_emit_rtm_html_shows_coverage_pct(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_html

    emit_rtm_html(minimal_rtm, runs_dir=tmp_path, feature_id="feat-pct-html")
    content = (tmp_path / "feat-pct-html" / "rtm.html").read_text()

    assert "100" in content or "1.0" in content or "100.0%" in content


def test_emit_rtm_json_returns_path(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_json

    result = emit_rtm_json(minimal_rtm, runs_dir=tmp_path, feature_id="feat-ret")

    assert isinstance(result, pathlib.Path)


def test_emit_rtm_html_returns_path(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_html

    result = emit_rtm_html(minimal_rtm, runs_dir=tmp_path, feature_id="feat-ret-html")

    assert isinstance(result, pathlib.Path)

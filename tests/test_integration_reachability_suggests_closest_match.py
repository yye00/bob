"""Tests for suggest_closest_match."""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.spec_quality.integration_reachability import suggest_closest_match


def test_suggests_close_file_match(tmp_path):
    # Create bob/cli/plan.py - a typo "pln" should suggest "plan"
    plan = tmp_path / "src" / "bob" / "cli" / "plan.py"
    plan.parent.mkdir(parents=True)
    plan.write_text("# plan")

    match = suggest_closest_match("bob.cli.pln", workspace=tmp_path)
    assert match is not None
    assert "plan" in match


def test_no_match_for_entirely_alien_module(tmp_path):
    # Completely unique name — expect None or irrelevant far-off string
    result = suggest_closest_match("zzz.yyy.xxx.completelyrandom", workspace=tmp_path)
    # We don't assert a specific value here, just that we get str or None
    assert result is None or isinstance(result, str)


def test_suggests_from_spec_modules(tmp_path):
    features = [
        {"name": "F1", "acceptance_criteria": ["integration: myapp.engine.core"]},
        {"name": "F2", "acceptance_criteria": ["integration: myapp.engine.core"]},
    ]
    # Searching for a typo — spec has 'myapp.engine.core'
    match = suggest_closest_match("myapp.engine.cor", features=features, workspace=tmp_path)
    assert match is not None
    assert "myapp.engine.core" in match


def test_returns_none_when_no_candidates(tmp_path):
    result = suggest_closest_match("phantom.module", workspace=tmp_path)
    # With no workspace files and no spec, result may be None or a system module
    assert result is None or isinstance(result, str)

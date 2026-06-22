"""Tests for handle_empty_registry — zero/empty boundary."""

from __future__ import annotations

import pytest
from pathlib import Path

from bob3.spec_quality.spec_findings_registry import handle_empty_registry


class TestHandleEmptyRegistry:
    def test_returns_zero_when_file_missing(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        assert not fp.exists()
        rate = handle_empty_registry(findings_path=fp)
        assert rate == 0.0

    def test_returns_zero_when_registry_has_zero_entries(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        fp.write_text("schema_version: 2\nfindings: {}\nrun_history: []\n")
        rate = handle_empty_registry(findings_path=fp)
        assert rate == 0.0

    def test_returns_float(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        rate = handle_empty_registry(findings_path=fp)
        assert isinstance(rate, float)

    def test_zero_is_exactly_zero_not_nan(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        rate = handle_empty_registry(findings_path=fp)
        assert rate == 0.0
        assert rate == rate  # not NaN

    def test_returns_zero_for_empty_yaml_content(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        fp.write_text("")
        rate = handle_empty_registry(findings_path=fp)
        assert rate == 0.0

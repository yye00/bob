"""Tests for reject_no_coverage_uplift — raises NoCoverageUpliftError on coverage-empty tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob.orchestrator.test_writer_agent import (
    NoCoverageUpliftError,
    emit_failing_tests,
    reject_no_coverage_uplift,
)


class TestRejectNoCoverageUplift:
    def test_raises_for_test_with_only_assert_true(self, tmp_path):
        """A test with only assert True doesn't reference any real code region."""
        vacuous = tmp_path / "test_vacuous_cov.py"
        vacuous.write_text(
            "def test_nothing():\n    assert True\n",
            encoding="utf-8",
        )
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(vacuous)

    def test_does_not_raise_for_pytest_fail_call(self, tmp_path):
        """A test calling pytest.fail() references a non-trivial symbol — passes heuristic."""
        good = tmp_path / "test_with_pytest_fail.py"
        good.write_text(
            "import pytest\ndef test_x():\n    pytest.fail('not done')\n",
            encoding="utf-8",
        )
        # Should not raise
        reject_no_coverage_uplift(good)

    def test_does_not_raise_for_non_pytest_import(self, tmp_path):
        """A test importing a real module references the codebase — passes heuristic."""
        good = tmp_path / "test_with_import.py"
        good.write_text(
            "import os\nimport pytest\ndef test_x():\n    pytest.fail('not done')\n",
            encoding="utf-8",
        )
        # Should not raise
        reject_no_coverage_uplift(good)

    def test_raises_when_ac_region_not_in_source(self, tmp_path):
        """When ac_region is provided, the test must reference that region string."""
        good_heuristic = tmp_path / "test_region_check.py"
        good_heuristic.write_text(
            "import pytest\ndef test_x():\n    pytest.fail('not done')\n",
            encoding="utf-8",
        )
        with pytest.raises(NoCoverageUpliftError, match="bob.mymodule.my_function"):
            reject_no_coverage_uplift(good_heuristic, ac_region="bob.mymodule.my_function")

    def test_does_not_raise_when_ac_region_present_in_source(self, tmp_path):
        """When ac_region is in the test source, the coverage check passes."""
        good = tmp_path / "test_region_present.py"
        good.write_text(
            "import pytest\n# Tests: bob.mymodule.my_function\ndef test_x():\n    pytest.fail('not done')\n",
            encoding="utf-8",
        )
        # Should not raise
        reject_no_coverage_uplift(good, ac_region="bob.mymodule.my_function")

    def test_error_message_mentions_path(self, tmp_path):
        """NoCoverageUpliftError message should include the test path."""
        vacuous = tmp_path / "test_coverage_msg.py"
        vacuous.write_text(
            "def test_x():\n    assert True\n",
            encoding="utf-8",
        )
        with pytest.raises(NoCoverageUpliftError, match="test_coverage_msg"):
            reject_no_coverage_uplift(vacuous)

    def test_accepts_string_path(self, tmp_path):
        """reject_no_coverage_uplift should accept a string path."""
        good = tmp_path / "test_str_path_cov.py"
        good.write_text(
            "import pytest\ndef test_x():\n    pytest.fail('not done')\n",
            encoding="utf-8",
        )
        # Should not raise
        reject_no_coverage_uplift(str(good))

    def test_emitted_template_passes_coverage_heuristic(self, tmp_path):
        """emit_failing_tests output calls pytest.fail — passes heuristic."""
        acs = ["File exists: src/mymod.py"]
        emitted = emit_failing_tests("feat-cov-check", acs, workspace=tmp_path)
        # Should not raise
        reject_no_coverage_uplift(emitted[0].test_path)

    def test_no_coverage_uplift_error_is_exception(self):
        """NoCoverageUpliftError must be a subclass of Exception."""
        assert issubclass(NoCoverageUpliftError, Exception)

    def test_raises_for_empty_test_body(self, tmp_path):
        """An empty test body (pass) has no coverage uplift."""
        empty = tmp_path / "test_empty_cov.py"
        empty.write_text(
            "def test_empty():\n    pass\n",
            encoding="utf-8",
        )
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(empty)

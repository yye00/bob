"""Error-path tests for bob.build_verification (feature f3523d60).

Invalid input must raise ValueError and the function must not silently succeed.

AC: pytest: tests/test_cmake_ninja_build_verification_gate_build_ac_kind_error.py
"""

from __future__ import annotations

import pytest

from bob.build_verification import is_cmake_project, run_build_criterion


class TestRunBuildCriterionErrors:
    def test_none_workspace_raises(self):
        with pytest.raises(ValueError):
            run_build_criterion(None, "", kind="build")

    def test_non_str_pathlike_workspace_raises(self):
        with pytest.raises(ValueError):
            run_build_criterion(123, "", kind="build")

    def test_none_expression_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_build_criterion(tmp_path, None, kind="build")

    def test_non_str_expression_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_build_criterion(tmp_path, ["build"], kind="build")

    def test_invalid_kind_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_build_criterion(tmp_path, "", kind="not_a_kind")

    def test_non_str_kind_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_build_criterion(tmp_path, "", kind=42)

    def test_zero_timeout_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_build_criterion(tmp_path, "", kind="build", timeout=0)

    def test_negative_timeout_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_build_criterion(tmp_path, "", kind="build", timeout=-30)

    def test_bool_timeout_raises(self, tmp_path):
        # bool is a subclass of int; must be rejected as a programmer error.
        with pytest.raises(ValueError):
            run_build_criterion(tmp_path, "", kind="build", timeout=True)


class TestIsCmakeProjectErrors:
    def test_none_raises(self):
        with pytest.raises(ValueError):
            is_cmake_project(None)

    def test_int_raises(self):
        with pytest.raises(ValueError):
            is_cmake_project(0)

"""Error-path tests for _check_criterion_with_details — F-R7-576.

Verifies that invalid input (e.g. non-string criterion) raises ValueError
and that the function does not silently succeed on bad input.
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.enhanced_verification import _check_criterion_with_details


def _call(criterion, tmp_path: pathlib.Path) -> tuple[bool, str]:
    return _check_criterion_with_details(
        criterion=criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


class TestInvalidInputRaisesValueError:
    """Error path: non-string criterion must raise ValueError, never silently succeed."""

    def test_none_criterion_raises(self, tmp_path):
        with pytest.raises((ValueError, TypeError)):
            _call(None, tmp_path)

    def test_integer_criterion_raises(self, tmp_path):
        with pytest.raises((ValueError, TypeError)):
            _call(42, tmp_path)

    def test_list_criterion_raises(self, tmp_path):
        with pytest.raises((ValueError, TypeError)):
            _call(["pytest:", "some test"], tmp_path)

    def test_dict_criterion_raises(self, tmp_path):
        with pytest.raises((ValueError, TypeError)):
            _call({"criterion": "pytest: tests/foo.py"}, tmp_path)

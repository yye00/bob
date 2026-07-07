"""Error path tests for bob.deterministic_pytest_snapshots.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.deterministic_pytest_snapshots import (
    build_snapshot_pytest_args,
    enforce_maxfail_zero,
)


class TestEnforceNonListInputRaisesValueError:
    """Non-list argv must raise ValueError, not silently succeed."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest --maxfail=0 tests/")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(("pytest", "tests/"))

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(42)

    def test_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero({"pytest": "tests/"})


class TestEnforceNonStringElementsRaisesValueError:
    """List elements that are not strings must raise ValueError."""

    def test_integer_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", 4, "tests/"])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None])

    def test_list_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", ["tests/"]])

    def test_bool_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", True])


class TestBuildInvalidArgvRaisesValueError:
    """build_snapshot_pytest_args rejects invalid argv identically."""

    def test_none_argv_raises(self):
        with pytest.raises(ValueError):
            build_snapshot_pytest_args(None)

    def test_string_argv_raises(self):
        with pytest.raises(ValueError):
            build_snapshot_pytest_args("pytest tests/")

    def test_non_string_element_raises(self):
        with pytest.raises(ValueError):
            build_snapshot_pytest_args(["pytest", 99])


class TestBuildInvalidNumprocessesRaisesValueError:
    """Invalid numprocesses must raise ValueError, not silently succeed."""

    def test_negative_numprocesses_raises(self):
        with pytest.raises(ValueError):
            build_snapshot_pytest_args(["pytest", "tests/"], numprocesses=-1)

    def test_string_numprocesses_raises(self):
        with pytest.raises(ValueError):
            build_snapshot_pytest_args(["pytest", "tests/"], numprocesses="4")

    def test_float_numprocesses_raises(self):
        with pytest.raises(ValueError):
            build_snapshot_pytest_args(["pytest", "tests/"], numprocesses=2.5)

    def test_bool_numprocesses_raises(self):
        # bool is a subclass of int but is not a valid worker count.
        with pytest.raises(ValueError):
            build_snapshot_pytest_args(["pytest", "tests/"], numprocesses=True)


class TestErrorMessageQuality:
    """ValueError messages must be informative, not silent failures."""

    def test_none_error_message_mentions_type(self):
        with pytest.raises(ValueError, match=r"list"):
            enforce_maxfail_zero(None)

    def test_integer_element_error_mentions_type(self):
        with pytest.raises(ValueError, match=r"str"):
            enforce_maxfail_zero(["pytest", 99])

    def test_numprocesses_error_informative(self):
        with pytest.raises(ValueError, match=r"numprocesses"):
            build_snapshot_pytest_args(["pytest"], numprocesses=-5)

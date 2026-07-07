"""Error-path cases for backend_required_check (feature c28dbe93).

Invalid input raises ValueError; the function does not silently succeed.
"""

import pytest

from hippy.backend_required_check import (
    is_harness_feature,
    backend_required_check,
)


def test_is_harness_non_string_title_raises():
    with pytest.raises(ValueError):
        is_harness_feature(123)


def test_is_harness_none_title_raises():
    with pytest.raises(ValueError):
        is_harness_feature(None)


def test_backend_required_non_string_title_raises():
    with pytest.raises(ValueError):
        backend_required_check(["not", "a", "string"])


def test_backend_required_none_title_raises():
    with pytest.raises(ValueError):
        backend_required_check(None)


def test_is_harness_non_string_description_raises():
    with pytest.raises(ValueError):
        is_harness_feature("xfail", description=42)

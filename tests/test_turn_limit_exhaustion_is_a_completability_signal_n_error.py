"""Error-path tests for bob.turn_limit_completability (182cf79c).

Invalid input raises ValueError and the function does not silently succeed.
"""
from __future__ import annotations

import pytest

from bob import turn_limit_completability as tlc


def test_is_turn_limit_rejects_int():
    with pytest.raises(ValueError):
        tlc.is_turn_limit_result(123)


def test_is_turn_limit_rejects_list():
    with pytest.raises(ValueError):
        tlc.is_turn_limit_result([1, 2, 3])


def test_is_transport_transient_rejects_int():
    with pytest.raises(ValueError):
        tlc.is_transport_transient(42)


def test_is_transport_transient_rejects_list():
    with pytest.raises(ValueError):
        tlc.is_transport_transient(["econnreset"])


def test_classify_result_rejects_int():
    with pytest.raises(ValueError):
        tlc.classify_result(999)


def test_classify_result_rejects_float():
    with pytest.raises(ValueError):
        tlc.classify_result(3.14)

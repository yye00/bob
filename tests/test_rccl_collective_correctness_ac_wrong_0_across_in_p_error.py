"""Error-path tests for bob.rccl_correctness (feature fdd2060d).

Invalid input raises ValueError and the function does not silently succeed.
"""
from __future__ import annotations

import pytest

from bob.rccl_correctness import parse_wrong_column, verify_rccl_correct


# ---------------------------------------------------------------- parse_wrong_column


def test_parse_non_str_raises():
    with pytest.raises(ValueError):
        parse_wrong_column(12345)  # type: ignore[arg-type]


def test_parse_none_raises():
    with pytest.raises(ValueError):
        parse_wrong_column(None)  # type: ignore[arg-type]


def test_parse_bytes_raises():
    with pytest.raises(ValueError):
        parse_wrong_column(b"# nGpus 8")  # type: ignore[arg-type]


# ---------------------------------------------------------------- verify_rccl_correct


def test_verify_non_str_output_raises():
    with pytest.raises(ValueError):
        verify_rccl_correct(123, min_ranks=8, min_bytes=8, max_bytes=16)  # type: ignore[arg-type]


def test_verify_negative_min_ranks_raises():
    with pytest.raises(ValueError):
        verify_rccl_correct("", min_ranks=-1, min_bytes=8, max_bytes=16)


def test_verify_bool_min_ranks_raises():
    with pytest.raises(ValueError):
        verify_rccl_correct("", min_ranks=True, min_bytes=8, max_bytes=16)


def test_verify_negative_min_bytes_raises():
    with pytest.raises(ValueError):
        verify_rccl_correct("", min_ranks=8, min_bytes=-8, max_bytes=16)


def test_verify_max_less_than_min_bytes_raises():
    with pytest.raises(ValueError):
        verify_rccl_correct("", min_ranks=8, min_bytes=64, max_bytes=8)


def test_verify_non_int_max_bytes_raises():
    with pytest.raises(ValueError):
        verify_rccl_correct("", min_ranks=8, min_bytes=8, max_bytes="16")  # type: ignore[arg-type]

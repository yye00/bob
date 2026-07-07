"""Boundary tests for bob.rccl_correctness (feature fdd2060d).

Empty, zero, or minimum input must return a well-defined result rather than
raising.
"""
from __future__ import annotations

from bob.rccl_correctness import (
    WrongColumnReport,
    CorrectnessVerdict,
    parse_wrong_column,
    verify_rccl_correct,
)


def test_parse_empty_output_returns_report():
    rep = parse_wrong_column("")
    assert isinstance(rep, WrongColumnReport)
    assert rep.rows == []
    assert rep.all_correct is False  # no evidence => not proven correct


def test_parse_whitespace_only_output():
    rep = parse_wrong_column("   \n\n   \n")
    assert isinstance(rep, WrongColumnReport)
    assert rep.rows == []


def test_parse_header_only_no_rows():
    header = (
        "# nThread 1 nGpus 8 minBytes 8 maxBytes 134217728 "
        "step: 2(factor) warmup iters: 5 iters: 20 validation: 1\n"
    )
    rep = parse_wrong_column(header)
    assert rep.rows == []
    assert rep.header.n_gpus == 8


def test_parse_single_minimum_row():
    out = (
        "# nThread 1 nGpus 2 minBytes 8 maxBytes 8 "
        "step: 2(factor) warmup iters: 5 iters: 20 validation: 1\n"
        "           8             2     float     sum    "
        "12.34    0.00    0.00       0    11.00    0.00    0.00       0\n"
    )
    rep = parse_wrong_column(out)
    assert len(rep.rows) == 1
    assert rep.rows[0].size == 8
    assert rep.all_correct is True
    assert rep.max_wrong == 0


def test_verify_empty_output_returns_failing_verdict():
    v = verify_rccl_correct("", min_ranks=8, min_bytes=8, max_bytes=134217728)
    assert isinstance(v, CorrectnessVerdict)
    assert v.passed is False


def test_verify_zero_min_ranks_still_defined():
    out = (
        "# nThread 1 nGpus 2 minBytes 8 maxBytes 8 "
        "step: 2(factor) warmup iters: 5 iters: 20 validation: 1\n"
        "           8             2     float     sum    "
        "12.34    0.00    0.00       0    11.00    0.00    0.00       0\n"
    )
    v = verify_rccl_correct(out, min_ranks=0, min_bytes=8, max_bytes=8)
    assert isinstance(v, CorrectnessVerdict)
    assert v.passed is True


def test_report_as_dict_on_empty():
    d = parse_wrong_column("").as_dict()
    assert d["rows"] == []
    assert d["all_correct"] is False

"""Tests for bob.rccl_correctness (feature fdd2060d).

RCCL collective-correctness AC: parse the tabular ``#wrong`` column from a
freshly executed rccl-tests benchmark (e.g. ``all_reduce_perf -c 1``) and
require it to be exactly 0 for BOTH the out-of-place and in-place variants
across the entire size sweep, while enforcing anti-gaming header preconditions.
"""
from __future__ import annotations

import pytest

from bob.rccl_correctness import (
    WrongColumnReport,
    WrongHeader,
    WrongRow,
    CorrectnessVerdict,
    parse_wrong_column,
    verify_rccl_correct,
)

# A realistic all_reduce_perf -c 1 output over a power-of-two sweep, all correct.
_GOOD_OUTPUT = """\
# nThread 1 nGpus 8 minBytes 8 maxBytes 134217728 step: 2(factor) warmup iters: 5 iters: 20 validation: 1
#
#                                                              out-of-place                       in-place
#       size         count      type   redop     time   algbw   busbw  #wrong     time   algbw   busbw  #wrong
#        (B)    (elements)                       (us)  (GB/s)  (GB/s)            (us)  (GB/s)  (GB/s)
           8             2     float     sum    12.34    0.00    0.00       0    11.00    0.00    0.00       0
          16             4     float     sum    12.00    0.00    0.00       0    11.10    0.00    0.00       0
     3145728        786432     float     sum    45.00   69.90  122.30       0    44.00   71.50  125.10       0
   134217728      33554432     float     sum   999.00  134.30  235.00       0   998.00  134.40  235.10       0
# Out of bounds values : 0 OK
# Avg bus bandwidth    : 179.40
"""

# Same shape but out-of-place #wrong is non-zero on the 3MB (non-pow2) row.
_WRONG_OOP_OUTPUT = """\
# nThread 1 nGpus 8 minBytes 8 maxBytes 134217728 step: 2(factor) warmup iters: 5 iters: 20 validation: 1
#
#                                                              out-of-place                       in-place
#       size         count      type   redop     time   algbw   busbw  #wrong     time   algbw   busbw  #wrong
           8             2     float     sum    12.34    0.00    0.00       0    11.00    0.00    0.00       0
     3145728        786432     float     sum    45.00   69.90  122.30       7    44.00   71.50  125.10       0
"""

# in-place #wrong non-zero.
_WRONG_IP_OUTPUT = """\
# nThread 1 nGpus 8 minBytes 8 maxBytes 134217728 step: 2(factor) warmup iters: 5 iters: 20 validation: 1
           8             2     float     sum    12.34    0.00    0.00       0    11.00    0.00    0.00       3
"""

# Asterisked out-of-bounds entry (busbw flagged) — must fail.
_ASTERISK_OUTPUT = """\
# nThread 1 nGpus 8 minBytes 8 maxBytes 134217728 step: 2(factor) warmup iters: 5 iters: 20 validation: 1
           8             2     float     sum    12.34    0.00   1e-07*      0    11.00    0.00    0.00       0
"""


# ---------------------------------------------------------------- parse_wrong_column


def test_parse_returns_report():
    rep = parse_wrong_column(_GOOD_OUTPUT)
    assert isinstance(rep, WrongColumnReport)
    assert isinstance(rep.header, WrongHeader)
    assert all(isinstance(r, WrongRow) for r in rep.rows)


def test_parse_header_fields():
    rep = parse_wrong_column(_GOOD_OUTPUT)
    assert rep.header.n_gpus == 8
    assert rep.header.n_ranks == 8
    assert rep.header.min_bytes == 8
    assert rep.header.max_bytes == 134217728
    assert rep.header.validation_enabled is True


def test_parse_extracts_all_data_rows():
    rep = parse_wrong_column(_GOOD_OUTPUT)
    assert len(rep.rows) == 4
    sizes = [r.size for r in rep.rows]
    assert sizes == [8, 16, 3145728, 134217728]


def test_parse_wrong_columns_zero_when_correct():
    rep = parse_wrong_column(_GOOD_OUTPUT)
    for r in rep.rows:
        assert r.out_of_place_wrong == 0
        assert r.in_place_wrong == 0
    assert rep.all_correct is True
    assert rep.max_wrong == 0


def test_parse_detects_out_of_place_wrong():
    rep = parse_wrong_column(_WRONG_OOP_OUTPUT)
    bad = [r for r in rep.rows if r.out_of_place_wrong > 0]
    assert len(bad) == 1
    assert bad[0].size == 3145728
    assert bad[0].out_of_place_wrong == 7
    assert rep.all_correct is False


def test_parse_detects_in_place_wrong():
    rep = parse_wrong_column(_WRONG_IP_OUTPUT)
    assert rep.rows[0].in_place_wrong == 3
    assert rep.all_correct is False


def test_parse_detects_asterisked_out_of_bounds():
    rep = parse_wrong_column(_ASTERISK_OUTPUT)
    assert rep.rows[0].out_of_bounds is True
    assert rep.all_correct is False


def test_parse_captures_row_dtype_and_redop():
    rep = parse_wrong_column(_GOOD_OUTPUT)
    assert rep.rows[0].dtype == "float"
    assert rep.rows[0].redop == "sum"


def test_parse_report_as_dict_roundtrips():
    rep = parse_wrong_column(_GOOD_OUTPUT)
    d = rep.as_dict()
    assert d["all_correct"] is True
    assert d["header"]["n_gpus"] == 8
    assert len(d["rows"]) == 4


# ---------------------------------------------------------------- verify_rccl_correct


def test_verify_passes_on_clean_run():
    v = verify_rccl_correct(_GOOD_OUTPUT, min_ranks=8, min_bytes=8, max_bytes=134217728)
    assert isinstance(v, CorrectnessVerdict)
    assert v.passed is True
    assert v.wrong_total == 0


def test_verify_fails_on_out_of_place_wrong():
    v = verify_rccl_correct(_WRONG_OOP_OUTPUT, min_ranks=8, min_bytes=8, max_bytes=134217728)
    assert v.passed is False
    assert v.wrong_total == 7
    assert "wrong" in v.reason.lower()


def test_verify_fails_on_in_place_wrong():
    v = verify_rccl_correct(_WRONG_IP_OUTPUT, min_ranks=8, min_bytes=8, max_bytes=134217728)
    assert v.passed is False
    assert v.wrong_total == 3


def test_verify_fails_on_asterisked_entry():
    v = verify_rccl_correct(_ASTERISK_OUTPUT, min_ranks=8, min_bytes=8, max_bytes=134217728)
    assert v.passed is False
    assert "bound" in v.reason.lower()


def test_verify_fails_when_ranks_collapsed():
    # anti-gaming: run header reports fewer ranks than the AC demanded.
    v = verify_rccl_correct(_GOOD_OUTPUT, min_ranks=16, min_bytes=8, max_bytes=134217728)
    assert v.passed is False
    assert "rank" in v.reason.lower()


def test_verify_fails_when_sweep_shrunk_on_max():
    # header maxBytes below the demanded max => sweep was trivially shrunk.
    v = verify_rccl_correct(_GOOD_OUTPUT, min_ranks=8, min_bytes=8, max_bytes=1073741823)
    assert v.passed is False
    assert "max" in v.reason.lower() or "sweep" in v.reason.lower()


def test_verify_fails_when_min_bytes_raised():
    # header minBytes above the demanded min => small sizes skipped.
    v = verify_rccl_correct(_GOOD_OUTPUT, min_ranks=8, min_bytes=1, max_bytes=134217728)
    assert v.passed is False


def test_verify_fails_when_validation_disabled():
    no_val = _GOOD_OUTPUT.replace("validation: 1", "validation: 0")
    v = verify_rccl_correct(no_val, min_ranks=8, min_bytes=8, max_bytes=134217728)
    assert v.passed is False
    assert "validation" in v.reason.lower()


def test_verify_fails_when_no_data_rows():
    header_only = (
        "# nThread 1 nGpus 8 minBytes 8 maxBytes 134217728 "
        "step: 2(factor) warmup iters: 5 iters: 20 validation: 1\n"
    )
    v = verify_rccl_correct(header_only, min_ranks=8, min_bytes=8, max_bytes=134217728)
    assert v.passed is False


def test_verify_verdict_as_dict():
    v = verify_rccl_correct(_GOOD_OUTPUT, min_ranks=8, min_bytes=8, max_bytes=134217728)
    d = v.as_dict()
    assert d["passed"] is True
    assert d["wrong_total"] == 0
    assert "reason" in d

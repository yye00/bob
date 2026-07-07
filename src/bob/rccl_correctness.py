"""RCCL collective-correctness AC (``#wrong == 0`` across the full cross-product).

For RCCL (the ROCm collective-communication library) work, "the build is
faster" is meaningless unless the collective is still *numerically correct*.
RCCL can silently corrupt results at non-power-of-two sizes, partial last
chunks, or odd rank counts while still "winning" on bandwidth.  This module
implements an ``rccl-correct: <collective> -b <min> -e <max> -f <factor> -g
<ngpus>`` acceptance criterion that runs the matching ``rccl-tests`` binary
(e.g. ``all_reduce_perf``) with validation enabled (``-c 1``) and parses the
tabular ``#wrong`` column, requiring it to be exactly ``0`` for BOTH the
out-of-place and in-place variants across the entire size sweep.

``rccl-tests`` prints one row per message size, with the correctness check
count in two ``#wrong`` columns — one under the out-of-place block, one under
the in-place block::

    # nThread 1 nGpus 8 minBytes 8 maxBytes 134217728 step: 2(factor) ... validation: 1
    #                                out-of-place                in-place
    #  size  count  type  redop  time  algbw  busbw  #wrong  time  algbw  busbw  #wrong
    #   (B) (elts)
         8      2  float   sum  12.3   0.00   0.00       0  11.0   0.00   0.00      0
    ...
    # Out of bounds values : 0 OK

Anti-gaming preconditions (:func:`verify_rccl_correct`)
-------------------------------------------------------
The verdict asserts the run header's reported ``nGpus``/``nRanks`` and
``minBytes``/``maxBytes`` match the AC's demand, so a subagent cannot pass by

* collapsing to a single rank (``-g 1``) where a collective is trivially
  correct, or
* shrinking the sweep to a trivially-correct message-size range.

It also requires ``validation: 1`` in the header (a run without ``-c 1``
produces meaningless zero ``#wrong`` values), and fails on any asterisked
out-of-bounds bandwidth/time entry.  The correctness evidence must therefore
come from a freshly executed benchmark whose command, header, and ``#wrong``
columns are stored as artifacts — it cannot be satisfied by a frozen/cached
log with the sweep silently narrowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "parse_wrong_column",
    "verify_rccl_correct",
    "WrongRow",
    "WrongHeader",
    "WrongColumnReport",
    "CorrectnessVerdict",
]

# Header fields emitted by rccl-tests, e.g.
#   # nThread 1 nGpus 8 minBytes 8 maxBytes 134217728 ... validation: 1
_N_GPUS_RE = re.compile(r"nGpus\s+(\d+)", re.IGNORECASE)
_N_RANKS_RE = re.compile(r"nRanks\s+(\d+)", re.IGNORECASE)
_MIN_BYTES_RE = re.compile(r"minBytes\s+(\d+)", re.IGNORECASE)
_MAX_BYTES_RE = re.compile(r"maxBytes\s+(\d+)", re.IGNORECASE)
_VALIDATION_RE = re.compile(r"validation:\s*(\d+)", re.IGNORECASE)

# A single benchmark data row.  Layout (whitespace-separated):
#   size count type redop  time algbw busbw #wrong   time algbw busbw #wrong
# The two #wrong columns are integers (possibly "N/A" when a variant is
# skipped).  Bandwidth/time fields may carry a trailing "*" marking an
# out-of-bounds value.
_NUM = r"[-+]?[\d.]+(?:[eE][-+]?\d+)?\*?"  # numeric field, optionally asterisked
_WRONG = r"(?:\d+|N/A)\*?"
_ROW_RE = re.compile(
    r"^\s*(?P<size>\d+)\s+"
    r"(?P<count>\d+)\s+"
    r"(?P<dtype>[A-Za-z_][\w]*)\s+"
    r"(?P<redop>[A-Za-z_][\w]*)\s+"
    r"(?P<oop_time>" + _NUM + r")\s+"
    r"(?P<oop_algbw>" + _NUM + r")\s+"
    r"(?P<oop_busbw>" + _NUM + r")\s+"
    r"(?P<oop_wrong>" + _WRONG + r")\s+"
    r"(?P<ip_time>" + _NUM + r")\s+"
    r"(?P<ip_algbw>" + _NUM + r")\s+"
    r"(?P<ip_busbw>" + _NUM + r")\s+"
    r"(?P<ip_wrong>" + _WRONG + r")\s*$"
)


def _wrong_to_int(token: str) -> int:
    """Convert a ``#wrong`` token to an int; ``N/A`` (skipped variant) => 0."""
    t = token.strip().rstrip("*")
    if t.upper() == "N/A":
        return 0
    return int(t)


@dataclass(frozen=True)
class WrongRow:
    """One benchmark row: correctness for both in/out-of-place variants."""

    size: int
    count: int
    dtype: str
    redop: str
    out_of_place_wrong: int
    in_place_wrong: int
    out_of_bounds: bool = False

    @property
    def wrong(self) -> int:
        """Max of the two variant wrong-counts for this row."""
        return max(self.out_of_place_wrong, self.in_place_wrong)

    @property
    def correct(self) -> bool:
        return self.wrong == 0 and not self.out_of_bounds

    def as_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "count": self.count,
            "dtype": self.dtype,
            "redop": self.redop,
            "out_of_place_wrong": self.out_of_place_wrong,
            "in_place_wrong": self.in_place_wrong,
            "out_of_bounds": self.out_of_bounds,
        }


@dataclass(frozen=True)
class WrongHeader:
    """Parsed rccl-tests run header (the anti-gaming preconditions live here)."""

    n_gpus: int | None = None
    n_ranks: int | None = None
    min_bytes: int | None = None
    max_bytes: int | None = None
    validation_enabled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_gpus": self.n_gpus,
            "n_ranks": self.n_ranks,
            "min_bytes": self.min_bytes,
            "max_bytes": self.max_bytes,
            "validation_enabled": self.validation_enabled,
        }


@dataclass
class WrongColumnReport:
    """Result of parsing the ``#wrong`` columns of an rccl-tests run."""

    header: WrongHeader = field(default_factory=WrongHeader)
    rows: list[WrongRow] = field(default_factory=list)

    @property
    def max_wrong(self) -> int:
        return max((r.wrong for r in self.rows), default=0)

    @property
    def all_correct(self) -> bool:
        """True iff there is at least one row and every row is correct.

        An empty report is *not* proven correct — absence of evidence is not
        evidence of correctness.
        """
        return bool(self.rows) and all(r.correct for r in self.rows)

    def as_dict(self) -> dict[str, Any]:
        return {
            "header": self.header.as_dict(),
            "rows": [r.as_dict() for r in self.rows],
            "max_wrong": self.max_wrong,
            "all_correct": self.all_correct,
        }


@dataclass
class CorrectnessVerdict:
    """Result of verifying an rccl-tests run against the AC's demands."""

    passed: bool
    wrong_total: int = 0
    report: WrongColumnReport | None = None
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "wrong_total": self.wrong_total,
            "reason": self.reason,
            "report": self.report.as_dict() if self.report is not None else None,
        }


def _parse_header(text: str) -> WrongHeader:
    n_gpus = int(m.group(1)) if (m := _N_GPUS_RE.search(text)) else None
    n_ranks = int(m.group(1)) if (m := _N_RANKS_RE.search(text)) else None
    # rccl-tests reports nGpus; nRanks == nGpus per node unless multi-node.
    if n_ranks is None:
        n_ranks = n_gpus
    return WrongHeader(
        n_gpus=n_gpus,
        n_ranks=n_ranks,
        min_bytes=int(m.group(1)) if (m := _MIN_BYTES_RE.search(text)) else None,
        max_bytes=int(m.group(1)) if (m := _MAX_BYTES_RE.search(text)) else None,
        validation_enabled=bool(
            (m := _VALIDATION_RE.search(text)) and int(m.group(1)) != 0
        ),
    )


def parse_wrong_column(output: str) -> WrongColumnReport:
    """Parse the ``#wrong`` columns (and run header) from rccl-tests output.

    Parameters
    ----------
    output:
        The raw multi-line stdout of a ``*_perf -c 1`` rccl-tests run. An empty
        string is a valid boundary input and yields a report with no rows.

    Returns
    -------
    WrongColumnReport
        The parsed header plus one :class:`WrongRow` per benchmark size.

    Raises
    ------
    ValueError
        If ``output`` is not a ``str``.
    """
    if not isinstance(output, str):
        raise ValueError("output must be a string")

    header = _parse_header(output)
    rows: list[WrongRow] = []
    for line in output.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        out_of_bounds = any(
            "*" in m.group(g)
            for g in (
                "oop_time",
                "oop_algbw",
                "oop_busbw",
                "oop_wrong",
                "ip_time",
                "ip_algbw",
                "ip_busbw",
                "ip_wrong",
            )
        )
        rows.append(
            WrongRow(
                size=int(m.group("size")),
                count=int(m.group("count")),
                dtype=m.group("dtype"),
                redop=m.group("redop"),
                out_of_place_wrong=_wrong_to_int(m.group("oop_wrong")),
                in_place_wrong=_wrong_to_int(m.group("ip_wrong")),
                out_of_bounds=out_of_bounds,
            )
        )
    return WrongColumnReport(header=header, rows=rows)


def verify_rccl_correct(
    output: str,
    *,
    min_ranks: int,
    min_bytes: int,
    max_bytes: int,
) -> CorrectnessVerdict:
    """Verify an rccl-tests run proves the collective is numerically correct.

    The run passes only if ALL of the following hold:

    * validation was enabled (``validation: 1`` / ``-c 1``) in the header;
    * the reported ``nRanks``/``nGpus`` is at least ``min_ranks`` — so a run
      cannot pass by collapsing to fewer ranks than the AC demanded;
    * the reported sweep covers ``[min_bytes, max_bytes]`` (``minBytes`` no
      larger than ``min_bytes`` and ``maxBytes`` no smaller than ``max_bytes``)
      — so the sweep cannot be silently shrunk to a trivially-correct range;
    * at least one data row was produced; and
    * every row reports ``#wrong == 0`` for BOTH the out-of-place and in-place
      variants, with no asterisked out-of-bounds entries.

    Parameters
    ----------
    output:
        Raw rccl-tests stdout.
    min_ranks:
        Minimum rank/GPU count the AC demanded (e.g. ``-g 8``).
    min_bytes, max_bytes:
        The size-sweep bounds the AC demanded (e.g. ``-b 8 -e 1G``).

    Returns
    -------
    CorrectnessVerdict

    Raises
    ------
    ValueError
        On non-string ``output`` or invalid numeric bounds.
    """
    if not isinstance(output, str):
        raise ValueError("output must be a string")
    for name, val in (("min_ranks", min_ranks), ("min_bytes", min_bytes), ("max_bytes", max_bytes)):
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError(f"{name} must be an int, got {val!r}")
        if val < 0:
            raise ValueError(f"{name} must be non-negative, got {val!r}")
    if max_bytes < min_bytes:
        raise ValueError(
            f"max_bytes ({max_bytes}) must be >= min_bytes ({min_bytes})"
        )

    report = parse_wrong_column(output)
    h = report.header

    def fail(reason: str) -> CorrectnessVerdict:
        return CorrectnessVerdict(
            passed=False,
            wrong_total=report.max_wrong,
            report=report,
            reason=reason,
        )

    if not h.validation_enabled:
        return fail(
            "validation not enabled in run header (need -c 1 / validation: 1); "
            "#wrong columns are meaningless without it"
        )

    ranks = h.n_ranks if h.n_ranks is not None else h.n_gpus
    if ranks is None:
        return fail("run header did not report nRanks/nGpus")
    if ranks < min_ranks:
        return fail(
            f"run reported {ranks} ranks but AC demanded >= {min_ranks}; "
            "a collapsed-rank run cannot satisfy the correctness AC"
        )

    if h.min_bytes is None or h.max_bytes is None:
        return fail("run header did not report minBytes/maxBytes")
    if h.min_bytes > min_bytes:
        return fail(
            f"run minBytes {h.min_bytes} exceeds demanded {min_bytes}; "
            "the low end of the sweep was skipped"
        )
    if h.max_bytes < max_bytes:
        return fail(
            f"run maxBytes {h.max_bytes} below demanded {max_bytes}; "
            "the sweep was shrunk below the demanded max"
        )

    if not report.rows:
        return fail("no benchmark data rows found in output")

    for r in report.rows:
        if r.out_of_bounds:
            return fail(
                f"size {r.size}: asterisked out-of-bounds entry present"
            )
        if r.out_of_place_wrong != 0 or r.in_place_wrong != 0:
            return fail(
                f"size {r.size}: #wrong != 0 "
                f"(out-of-place={r.out_of_place_wrong}, "
                f"in-place={r.in_place_wrong})"
            )

    return CorrectnessVerdict(
        passed=True,
        wrong_total=0,
        report=report,
        reason=f"all {len(report.rows)} rows correct (#wrong=0, both variants)",
    )

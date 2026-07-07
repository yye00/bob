"""RCCL selection-log + ``rocprof`` execution proof (selection != execution).

RCCL (the ROCm collective-communication library, NCCL's AMD port) chooses its
algorithm/protocol at runtime from environment knobs and optional tuner-plugin
CSV rules.  A feature that *claims* a collective-comm speed-up must prove three
distinct things — bob's existing launch-evidence (a Python-side counter for
``hipModuleLaunchKernel``) proves none of them for RCCL, because RCCL work
happens inside a shared library, not in the feature's own source:

1. **freeze_rccl_env** — the full ``RCCL_*`` / ``NCCL_*`` environment is byte-for-byte
   identical between the OLD (baseline) and NEW (candidate) runs, except for the
   single gate knob under test.  The perf gate is only meaningful when every
   other knob is frozen; a win produced by silently flipping ``NCCL_PROTO`` on
   only one side is a cheat.

2. **parse_selection_log** — the ``NCCL_DEBUG=INFO`` /
   ``NCCL_DEBUG_SUBSYS=TUNING`` log actually shows the *intended*
   algorithm/protocol chosen at the benchmarked message sizes, and that
   ``TUNER: Initializing tuner...`` appeared (proving the tuner plugin loaded
   rather than being silently ignored).

3. **verify_rocprof_kernel_trace** — a ``rocprof`` kernel-name trace proves a
   DISTINCT new kernel symbol executed and serviced the benchmarked bytes with
   the gate ON, and a gate-off/gate-on differential confirms the win vanishes
   when the gate is OFF (a "win" already present with the gate OFF is not caused
   by this feature and fails it).

This is the RCCL analog of bob's kernel-launch evidence, but log/trace-based
rather than a source-level counter.

References
----------
* RCCL env knobs: ``NCCL_ALGO`` (Ring/Tree/CollnetChain/NVLS),
  ``NCCL_PROTO`` (Simple/LL/LL128 — LL128 carries a documented data-corruption
  caveat on some links and must be flagged), ``NCCL_TUNER_PLUGIN`` +
  ``NCCL_TUNER_CONFIG_PATH`` (CSV tuner rules), ``NCCL_DEBUG=INFO`` +
  ``NCCL_DEBUG_SUBSYS=TUNING`` (logs selected algo/proto).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

__all__ = [
    "parse_selection_log",
    "verify_rocprof_kernel_trace",
    "freeze_rccl_env",
    "SelectionReport",
    "SelectionRecord",
    "RocprofVerdict",
    "FrozenEnv",
    "RCCL_ENV_PREFIXES",
    "LL128_CAVEAT",
]

# Env-var name prefixes that govern RCCL/NCCL behaviour and therefore MUST be
# frozen identically between OLD and NEW perf runs.
RCCL_ENV_PREFIXES = ("NCCL_", "RCCL_")

# LL128 is faster but is documented to corrupt data on links that do not
# guarantee 128-bit atomic delivery; selecting it must raise a visible caveat.
LL128_CAVEAT = (
    "NCCL_PROTO=LL128 selected: LL128 can silently corrupt data on links "
    "that do not guarantee 128-bit flit atomicity — verify link support."
)

# A single tuner/selection decision extracted from an NCCL_DEBUG log line.
_SELECTION_RE = re.compile(
    r"(?:nBytes|bytes|size)[=\s:]+(?P<size>\d+).*?"
    r"algo(?:rithm)?[=\s:]+(?P<algo>[A-Za-z][A-Za-z0-9]*)"
    r".*?proto(?:col)?[=\s:]+(?P<proto>[A-Za-z][A-Za-z0-9]*)",
    re.IGNORECASE,
)
# Alternate ordering: "Selected algorithm Ring protocol Simple" with no size.
_SELECTION_NOSIZE_RE = re.compile(
    r"selected\s+algorithm\s+(?P<algo>[A-Za-z][A-Za-z0-9]*)\s+"
    r"protocol\s+(?P<proto>[A-Za-z][A-Za-z0-9]*)",
    re.IGNORECASE,
)
# Tuner-plugin load marker.
_TUNER_INIT_RE = re.compile(r"TUNER\b.*Initializing\s+tuner", re.IGNORECASE)

_VALID_ALGOS = {"ring", "tree", "collnet", "collnetchain", "collnetdirect", "nvls", "nvlstree"}
_VALID_PROTOS = {"simple", "ll", "ll128"}


@dataclass(frozen=True)
class SelectionRecord:
    """One algo/proto selection decision parsed from a debug log line."""

    algo: str
    proto: str
    size: int | None = None

    def matches(self, algo: str | None, proto: str | None) -> bool:
        if algo is not None and self.algo.lower() != algo.lower():
            return False
        if proto is not None and self.proto.lower() != proto.lower():
            return False
        return True


@dataclass
class SelectionReport:
    """Result of parsing an NCCL_DEBUG selection log."""

    tuner_loaded: bool = False
    records: list[SelectionRecord] = field(default_factory=list)
    expected_algo: str | None = None
    expected_proto: str | None = None
    target_sizes: tuple[int, ...] = ()
    matched_sizes: tuple[int, ...] = ()
    missing_sizes: tuple[int, ...] = ()
    warnings: list[str] = field(default_factory=list)

    @property
    def selection_confirmed(self) -> bool:
        """True iff the intended algo/proto was chosen at every target size.

        With no expectation set, confirmation only requires that *some*
        selection was observed.  With target sizes set, every target size must
        have a matching record.
        """
        if not self.records:
            return False
        if self.expected_algo is None and self.expected_proto is None:
            return True
        if self.target_sizes:
            return len(self.missing_sizes) == 0 and len(self.matched_sizes) > 0
        return any(
            r.matches(self.expected_algo, self.expected_proto) for r in self.records
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "tuner_loaded": self.tuner_loaded,
            "selection_confirmed": self.selection_confirmed,
            "records": [
                {"algo": r.algo, "proto": r.proto, "size": r.size} for r in self.records
            ],
            "expected_algo": self.expected_algo,
            "expected_proto": self.expected_proto,
            "target_sizes": list(self.target_sizes),
            "matched_sizes": list(self.matched_sizes),
            "missing_sizes": list(self.missing_sizes),
            "warnings": list(self.warnings),
        }


@dataclass
class RocprofVerdict:
    """Result of verifying a rocprof kernel-name trace."""

    passed: bool
    distinct_kernel: str | None = None
    bytes_serviced: int = 0
    gate_on_kernels: tuple[str, ...] = ()
    gate_off_kernels: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "distinct_kernel": self.distinct_kernel,
            "bytes_serviced": self.bytes_serviced,
            "gate_on_kernels": list(self.gate_on_kernels),
            "gate_off_kernels": list(self.gate_off_kernels),
            "reason": self.reason,
        }


@dataclass
class FrozenEnv:
    """A byte-frozen RCCL/NCCL environment snapshot."""

    frozen: dict[str, str]
    signature: str

    def as_dict(self) -> dict[str, Any]:
        return {"frozen": dict(self.frozen), "signature": self.signature}


def parse_selection_log(
    log_text: str,
    *,
    expected_algo: str | None = None,
    expected_proto: str | None = None,
    target_sizes: Iterable[int] | None = None,
) -> SelectionReport:
    """Parse an ``NCCL_DEBUG=INFO`` / ``SUBSYS=TUNING`` selection log.

    Confirms that the intended algorithm/protocol was actually chosen at the
    target message sizes and that the tuner plugin loaded
    (``TUNER: Initializing tuner...``).

    Parameters
    ----------
    log_text:
        The raw multi-line debug log emitted by RCCL. An empty string is a
        valid boundary input and yields a report with no records.
    expected_algo, expected_proto:
        The algo/proto the feature intended to select (e.g. ``"Ring"``,
        ``"LL128"``). ``None`` disables that half of the check.
    target_sizes:
        Message sizes (bytes) the benchmark used. When provided, every target
        size must have a matching selection record for
        :pyattr:`SelectionReport.selection_confirmed` to be true.

    Returns
    -------
    SelectionReport

    Raises
    ------
    ValueError
        If ``log_text`` is not a string, or a target size is not a
        non-negative integer, or an expected algo/proto is unrecognised.
    """
    if not isinstance(log_text, str):
        raise ValueError("log_text must be a string")
    if expected_algo is not None:
        if not isinstance(expected_algo, str) or not expected_algo.strip():
            raise ValueError("expected_algo must be a non-empty string or None")
        if expected_algo.strip().lower() not in _VALID_ALGOS:
            raise ValueError(
                f"unrecognised expected_algo {expected_algo!r}; "
                f"expected one of {sorted(_VALID_ALGOS)}"
            )
    if expected_proto is not None:
        if not isinstance(expected_proto, str) or not expected_proto.strip():
            raise ValueError("expected_proto must be a non-empty string or None")
        if expected_proto.strip().lower() not in _VALID_PROTOS:
            raise ValueError(
                f"unrecognised expected_proto {expected_proto!r}; "
                f"expected one of {sorted(_VALID_PROTOS)}"
            )

    sizes: tuple[int, ...] = ()
    if target_sizes is not None:
        collected: list[int] = []
        for s in target_sizes:
            if isinstance(s, bool) or not isinstance(s, int) or s < 0:
                raise ValueError(f"target size must be a non-negative int, got {s!r}")
            collected.append(s)
        sizes = tuple(collected)

    report = SelectionReport(
        expected_algo=expected_algo.strip() if expected_algo else None,
        expected_proto=expected_proto.strip() if expected_proto else None,
        target_sizes=sizes,
    )

    for line in log_text.splitlines():
        if _TUNER_INIT_RE.search(line):
            report.tuner_loaded = True
        m = _SELECTION_RE.search(line)
        if m:
            report.records.append(
                SelectionRecord(
                    algo=m.group("algo"),
                    proto=m.group("proto"),
                    size=int(m.group("size")),
                )
            )
            continue
        m2 = _SELECTION_NOSIZE_RE.search(line)
        if m2:
            report.records.append(
                SelectionRecord(algo=m2.group("algo"), proto=m2.group("proto"))
            )

    # LL128 data-corruption caveat.
    if any(r.proto.lower() == "ll128" for r in report.records) or (
        report.expected_proto and report.expected_proto.lower() == "ll128"
    ):
        report.warnings.append(LL128_CAVEAT)

    if sizes and (report.expected_algo or report.expected_proto):
        matched: list[int] = []
        for sz in sizes:
            hit = any(
                r.size == sz and r.matches(report.expected_algo, report.expected_proto)
                for r in report.records
            )
            if hit:
                matched.append(sz)
        report.matched_sizes = tuple(matched)
        report.missing_sizes = tuple(s for s in sizes if s not in matched)

    return report


def freeze_rccl_env(
    env: Mapping[str, str],
    *,
    gate_knob: str | None = None,
) -> FrozenEnv:
    """Byte-freeze the RCCL/NCCL subset of an environment for the perf gate.

    Extracts every ``NCCL_*`` / ``RCCL_*`` variable, canonicalises it into a
    stable, sorted signature so OLD and NEW runs can be compared byte-for-byte,
    and (optionally) excludes the single ``gate_knob`` under test — the only
    variable allowed to differ between the two sides of the gate.

    Parameters
    ----------
    env:
        A mapping of environment variables (e.g. ``os.environ``).
    gate_knob:
        Name of the one knob under test, excluded from the frozen signature so
        the gate can legitimately flip it.  Everything else must match.

    Returns
    -------
    FrozenEnv
        The frozen subset plus a deterministic signature string.

    Raises
    ------
    ValueError
        If ``env`` is not a mapping or any RCCL key/value is not a string.
    """
    if not isinstance(env, Mapping):
        raise ValueError("env must be a mapping of str -> str")
    if gate_knob is not None and (not isinstance(gate_knob, str) or not gate_knob.strip()):
        raise ValueError("gate_knob must be a non-empty string or None")

    frozen: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str):
            raise ValueError(f"env key must be a string, got {key!r}")
        if not key.startswith(RCCL_ENV_PREFIXES):
            continue
        if gate_knob is not None and key == gate_knob:
            continue
        if not isinstance(value, str):
            raise ValueError(f"env value for {key!r} must be a string, got {value!r}")
        frozen[key] = value

    signature = "\n".join(f"{k}={frozen[k]}" for k in sorted(frozen))
    return FrozenEnv(frozen=frozen, signature=signature)


def verify_rocprof_kernel_trace(
    gate_on_trace: Iterable[Mapping[str, Any]],
    gate_off_trace: Iterable[Mapping[str, Any]] | None = None,
    *,
    benchmarked_bytes: int,
    baseline_kernels: Iterable[str] | None = None,
) -> RocprofVerdict:
    """Verify a ``rocprof`` kernel-name trace proves distinct execution.

    A trace is a sequence of records, each with at least a ``"name"`` (kernel
    symbol) and a ``"bytes"`` count (bytes the kernel serviced). The verifier
    proves:

    1. A DISTINCT kernel symbol (not present in ``baseline_kernels`` / the
       gate-off trace) executed with the gate ON.
    2. That new kernel serviced at least ``benchmarked_bytes`` bytes.
    3. A gate-off/gate-on differential: the distinct kernel must NOT already be
       present with the gate OFF — a "win" visible with the gate off is not
       caused by this feature and fails.

    Parameters
    ----------
    gate_on_trace:
        Kernel trace captured with the feature's gate ON.
    gate_off_trace:
        Kernel trace captured with the gate OFF (baseline). Optional; when
        omitted, ``baseline_kernels`` supplies the comparison set.
    benchmarked_bytes:
        The number of bytes the benchmark moved; the distinct kernel must
        service at least this many.
    baseline_kernels:
        Extra baseline kernel names to treat as pre-existing.

    Returns
    -------
    RocprofVerdict

    Raises
    ------
    ValueError
        If ``benchmarked_bytes`` is not a non-negative int, or a trace record is
        malformed (missing/empty name, or non-int byte count).
    """
    if isinstance(benchmarked_bytes, bool) or not isinstance(benchmarked_bytes, int):
        raise ValueError("benchmarked_bytes must be an integer")
    if benchmarked_bytes < 0:
        raise ValueError("benchmarked_bytes must be non-negative")

    def _norm(trace: Iterable[Mapping[str, Any]], label: str) -> list[tuple[str, int]]:
        out: list[tuple[str, int]] = []
        for rec in trace:
            if not isinstance(rec, Mapping):
                raise ValueError(f"{label} trace record must be a mapping, got {rec!r}")
            name = rec.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{label} trace record missing a non-empty 'name'")
            nbytes = rec.get("bytes", 0)
            if isinstance(nbytes, bool) or not isinstance(nbytes, int) or nbytes < 0:
                raise ValueError(
                    f"{label} trace record 'bytes' must be a non-negative int"
                )
            out.append((name.strip(), nbytes))
        return out

    on = _norm(gate_on_trace, "gate_on")
    off = _norm(gate_off_trace, "gate_off") if gate_off_trace is not None else []

    baseline: set[str] = set()
    if baseline_kernels is not None:
        for k in baseline_kernels:
            if not isinstance(k, str) or not k.strip():
                raise ValueError("baseline_kernels entries must be non-empty strings")
            baseline.add(k.strip())
    off_names = {n for n, _ in off}
    baseline |= off_names

    on_names = tuple(n for n, _ in on)
    off_names_t = tuple(n for n, _ in off)

    if not on:
        return RocprofVerdict(
            passed=False,
            gate_on_kernels=on_names,
            gate_off_kernels=off_names_t,
            reason="gate-on trace is empty: no kernel executed",
        )

    # Bytes serviced by each distinct (new) kernel with the gate on.
    serviced: dict[str, int] = {}
    for name, nbytes in on:
        if name not in baseline:
            serviced[name] = serviced.get(name, 0) + nbytes

    if not serviced:
        return RocprofVerdict(
            passed=False,
            gate_on_kernels=on_names,
            gate_off_kernels=off_names_t,
            reason=(
                "no DISTINCT new kernel with the gate ON — every gate-on kernel "
                "is also present with the gate OFF/baseline; the claimed win is "
                "not caused by this feature"
            ),
        )

    # Pick the distinct kernel that serviced the most bytes.
    best_kernel = max(serviced, key=lambda k: serviced[k])
    best_bytes = serviced[best_kernel]

    if best_bytes < benchmarked_bytes:
        return RocprofVerdict(
            passed=False,
            distinct_kernel=best_kernel,
            bytes_serviced=best_bytes,
            gate_on_kernels=on_names,
            gate_off_kernels=off_names_t,
            reason=(
                f"distinct kernel {best_kernel!r} serviced {best_bytes} bytes, "
                f"below the benchmarked {benchmarked_bytes} bytes"
            ),
        )

    return RocprofVerdict(
        passed=True,
        distinct_kernel=best_kernel,
        bytes_serviced=best_bytes,
        gate_on_kernels=on_names,
        gate_off_kernels=off_names_t,
        reason=(
            f"distinct kernel {best_kernel!r} executed only with the gate ON and "
            f"serviced {best_bytes} bytes (>= {benchmarked_bytes} benchmarked)"
        ),
    )

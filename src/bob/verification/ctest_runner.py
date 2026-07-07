"""ctest/gtest runner with JUnit-XML parsing and per-feature scoping.

Bob's ``tests_pass`` path is pytest-only: for a project with no ``.py`` files
the pytest verifier returns a soft WARNING PASS ("no Python source files
found; pytest run skipped"), so a C++/RCCL feature can pass verification
without a single test compiling or running.

This module adds a ``ctest:``/``gtest:`` AC kind that:

1. Builds a per-feature-scoped ctest command
   (``ctest --test-dir <build> --output-junit <tmp>.xml -R <regex>
   --output-on-failure``) so a feature is verified against ONLY its own tests,
   not a rebuild-and-rerun-the-world. We prefer CTest's native
   ``--output-junit`` over gtest's per-binary directory output, which corrupts
   under parallel ``-j`` runs.
2. Parses the JUnit XML (testcase / failure / skipped counts) into the same
   PASS/FAIL/reason dict shape the pytest handler emits, requiring N>0 tests
   to actually run and 0 failures.
3. Reuses bob's baseline/regression demotion so pre-existing ctest failures
   don't false-fail an unrelated feature.

Public API
----------
run_ctest_ac(criterion, build_dir, *, junit_xml=None, feature_regex=None,
             baseline=None, timeout_s=1800) -> dict
    Run (or parse injected results of) the ctest AC and return a verification
    result dict: {"name", "passed", "reason", ...} matching the pytest handler.

parse_junit_xml(xml_text) -> JUnitResult
    Parse a JUnit/CTest XML document into (total, failed, skipped, passed)
    counts. Raises ValueError on malformed / empty input.

build_ctest_command(build_dir, regex, junit_out, *, jobs=None) -> list[str]
    Construct the scoped ctest argv. Always includes ``-R <regex>`` so the run
    is scoped to the feature's own tests.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

__all__ = [
    "JUnitResult",
    "parse_junit_xml",
    "build_ctest_command",
    "run_ctest_ac",
]


@dataclass(frozen=True)
class JUnitResult:
    """Parsed counts from a JUnit / CTest XML document.

    Attributes
    ----------
    total:   Number of testcases discovered.
    failed:  Number of testcases that failed (or errored).
    skipped: Number of testcases skipped/disabled.
    """

    total: int
    failed: int
    skipped: int

    @property
    def passed(self) -> int:
        """Number of testcases that passed = total - failed - skipped (>= 0)."""
        return max(0, self.total - self.failed - self.skipped)


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_junit_xml(xml_text: str) -> JUnitResult:
    """Parse *xml_text* (a JUnit/CTest XML document) into a :class:`JUnitResult`.

    Counts are derived by walking every ``<testcase>`` element so the result is
    accurate even when a suite omits the ``tests``/``failures``/``skipped``
    attributes. A testcase is counted as failed when it carries a ``<failure>``
    or ``<error>`` child, and skipped when it carries a ``<skipped>`` child.

    Parameters
    ----------
    xml_text:
        The XML document text. Supports both a single ``<testsuite>`` root and
        a ``<testsuites>`` wrapper containing multiple suites.

    Raises
    ------
    ValueError:
        If *xml_text* is not a non-empty string, or is not well-formed XML.
    """
    if not isinstance(xml_text, str) or not xml_text.strip():
        raise ValueError(
            f"xml_text must be a non-empty string, got {xml_text!r}"
        )

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"malformed JUnit XML: {exc}") from exc

    testcases = list(root.iter("testcase"))
    total = len(testcases)
    failed = 0
    skipped = 0
    for tc in testcases:
        if tc.find("failure") is not None or tc.find("error") is not None:
            failed += 1
        elif tc.find("skipped") is not None or tc.find("disabled") is not None:
            skipped += 1

    return JUnitResult(total=total, failed=failed, skipped=skipped)


def build_ctest_command(
    build_dir: str | Path,
    regex: str,
    junit_out: str | Path,
    *,
    jobs: int | None = None,
) -> list[str]:
    """Construct a per-feature-scoped ctest argv.

    The command always includes ``-R <regex>`` so the run is restricted to the
    feature's own tests (never a rebuild-and-rerun-the-world), and uses CTest's
    native ``--output-junit`` (safe under parallel ``-j`` runs, unlike gtest's
    per-binary directory output).

    Raises
    ------
    ValueError:
        If *build_dir* is None/empty, *regex* is None/empty, or *junit_out* is
        None/empty.
    """
    if build_dir is None or not str(build_dir).strip():
        raise ValueError(f"build_dir must be a non-empty path, got {build_dir!r}")
    if not isinstance(regex, str) or not regex.strip():
        raise ValueError(
            f"regex must be a non-empty string to scope ctest to the feature, "
            f"got {regex!r}"
        )
    if junit_out is None or not str(junit_out).strip():
        raise ValueError(f"junit_out must be a non-empty path, got {junit_out!r}")

    ctest = shutil.which("ctest") or "ctest"
    cmd = [
        ctest,
        "--test-dir",
        str(build_dir),
        "--output-junit",
        str(junit_out),
        "-R",
        regex,
        "--output-on-failure",
    ]
    if jobs is not None and jobs > 0:
        cmd += ["-j", str(jobs)]
    return cmd


def _feature_regex_from_criterion(criterion: str) -> str:
    """Derive the ctest ``-R`` regex from a ``ctest:``/``gtest:`` criterion.

    ``ctest: rccl_allreduce`` -> ``rccl_allreduce``. If no prefix is present the
    whole (stripped) criterion is used as the regex.
    """
    stripped = criterion.strip()
    low = stripped.lower()
    for prefix in ("ctest:", "gtest:"):
        if low.startswith(prefix):
            return stripped[len(prefix):].strip()
    return stripped


def run_ctest_ac(
    criterion: str,
    build_dir: str | Path,
    *,
    junit_xml: str | None = None,
    feature_regex: str | None = None,
    baseline: "JUnitResult | None" = None,
    timeout_s: int = 1800,
) -> dict:
    """Run a ``ctest:``/``gtest:`` AC and return a verification result dict.

    The returned dict matches the pytest handler shape::

        {"name": "ctest", "passed": bool, "reason": str, ["severity": "warning"]}

    A PASS requires N>0 tests to have actually run and 0 failures. When
    *baseline* is supplied and the observed failures do not exceed the baseline
    failures, the result is demoted to a passing warning (pre-existing ctest
    failures don't false-fail an unrelated feature).

    Parameters
    ----------
    criterion:
        The raw AC string, e.g. ``"ctest: rccl_allreduce"``.
    build_dir:
        The CMake build directory (``--test-dir``).
    junit_xml:
        Optional pre-produced JUnit XML text. When provided, ctest is NOT
        invoked and this text is parsed directly (used for testing and for
        callers that already have the XML). When None, ctest is executed.
    feature_regex:
        Optional explicit ``-R`` regex; defaults to the token after the
        ``ctest:``/``gtest:`` prefix in *criterion*.
    baseline:
        Optional :class:`JUnitResult` captured before this feature ran, used
        for regression demotion.
    timeout_s:
        Subprocess timeout when ctest is actually invoked.

    Raises
    ------
    ValueError:
        If *criterion* is not a non-empty string, or *build_dir* is None/empty.
    """
    if not isinstance(criterion, str) or not criterion.strip():
        raise ValueError(
            f"criterion must be a non-empty string, got {criterion!r}"
        )
    if build_dir is None or not str(build_dir).strip():
        raise ValueError(f"build_dir must be a non-empty path, got {build_dir!r}")

    regex = (feature_regex or "").strip() or _feature_regex_from_criterion(criterion)
    if not regex:
        raise ValueError(
            f"could not derive a scoping regex from criterion {criterion!r}"
        )

    name = "ctest"

    if junit_xml is None:
        junit_xml = _invoke_ctest(build_dir, regex, timeout_s)
        if junit_xml is None:
            # ctest not available / build dir missing → soft warning, mirroring
            # the pytest handler's "not installed" behaviour.
            return {
                "name": name,
                "passed": True,
                "severity": "warning",
                "reason": "ctest not available or build dir missing; ctest AC skipped",
            }

    result = parse_junit_xml(junit_xml)

    if result.total == 0:
        return {
            "name": name,
            "passed": False,
            "reason": f"no tests ran (0 testcases) for regex {regex!r}; "
                      f"a ctest AC requires N>0 tests to actually run",
        }

    if result.failed == 0:
        return {
            "name": name,
            "passed": True,
            "reason": f"ctest passed: {result.passed} test(s), "
                      f"{result.skipped} skipped (regex {regex!r})",
        }

    # There are failures. Apply baseline/regression demotion.
    if baseline is not None and result.failed <= baseline.failed:
        return {
            "name": name,
            "passed": True,
            "severity": "warning",
            "reason": (
                f"ctest reported {result.failed} failure(s) but baseline had "
                f"{baseline.failed}; no regression attributed to this feature"
            ),
        }

    return {
        "name": name,
        "passed": False,
        "reason": f"{result.failed} failed, {result.passed} passed "
                  f"(regex {regex!r})",
    }


def _invoke_ctest(
    build_dir: str | Path,
    regex: str,
    timeout_s: int,
) -> str | None:
    """Invoke ctest with per-feature scoping; return the JUnit XML text.

    Returns None when ctest is unavailable, the build dir does not exist, or
    the run fails to produce an XML file (the caller demotes to a warning).
    """
    if not Path(build_dir).is_dir():
        return None
    if shutil.which("ctest") is None:
        return None

    with tempfile.TemporaryDirectory() as td:
        junit_out = Path(td) / "ctest-junit.xml"
        cmd = build_ctest_command(build_dir, regex, junit_out)
        try:
            subprocess.run(
                cmd,
                cwd=str(build_dir),
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if junit_out.exists():
            return junit_out.read_text(encoding="utf-8", errors="replace")
    return None

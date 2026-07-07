"""bob.cpp_test_integrity_gate — C++ test-suite anti-cheat gate.

Beyond stub bodies, a C++ subagent can hide failures by:

  * renaming a gtest to the ``DISABLED_`` prefix (googletest skips it silently),
  * inserting ``GTEST_SKIP()`` in the body (reported as ``<skipped>``),
  * dropping a test from the ctest set (removing an ``add_test`` call).

None of these are visible to bob's Python-shaped gates. This module is the C++
analog of bob's mutation / no-cheat discipline applied to the *test suite itself*.

The gate operates on already-captured tool output (strings), so it is pure and
trivially testable. A caller wires it to real subprocess output:

  * ``<testbin> --gtest_list_tests``            -> ``list_tests_output``
  * ``<testbin> --gtest_filter=*DISABLED_*
      --gtest_also_run_disabled_tests
      --gtest_output=xml:...``                  -> ``check_disabled_tests_pass``
  * ``<testbin> --gtest_output=xml:...``        -> ``xml_output``
  * committed ``CTestTestfile.cmake`` vs. current -> ``ctest_baseline`` / ``ctest_current``

Public API
----------
check_test_integrity(list_tests_output, disabled_baseline, *,
                     xml_output=None, skipped_baseline=0,
                     ctest_baseline=None, ctest_current=None) -> dict
    Aggregate gate. Fails when new DISABLED_ tests appear beyond the allowlist,
    when skip counts exceed the reviewed baseline, or when a ctest was removed.

check_disabled_tests_pass(xml_output) -> dict
    Parse the force-run of disabled tests; fail if any disabled test failed
    (proves a DISABLED_ test is genuinely quarantined, not rot-hiding a failure).

check_ctest_set_diff(ctest_baseline, ctest_current) -> dict
    Diff ``add_test`` calls; fail if a test was removed from the ctest set.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree

__all__ = [
    "check_test_integrity",
    "check_disabled_tests_pass",
    "check_ctest_set_diff",
    "find_disabled_tests",
    "parse_gtest_list_tests",
    "parse_gtest_xml_skipped",
    "parse_ctest_add_tests",
]

_DISABLED_PREFIX = "DISABLED_"


def _require_str(value: object, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} must not be None")
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    return value


def parse_gtest_list_tests(output: str) -> list[str]:
    """Parse ``--gtest_list_tests`` output into fully-qualified test names.

    googletest prints a suite header (ends with ``.``) at column 0, then each
    test indented beneath it. Suite-level ``DISABLED_`` prefixes disable every
    test in the suite; test-level prefixes disable just that case.
    """
    output = _require_str(output, "list_tests_output")
    names: list[str] = []
    current_suite: str | None = None
    for raw in output.splitlines():
        if not raw.strip():
            continue
        # Ignore googletest banner lines like "Running main() from ...".
        if raw.lstrip().startswith("Running main"):
            continue
        if not raw[0].isspace():
            # Suite header — strip trailing "." and any trailing "# comment".
            header = raw.strip()
            header = header.split("#", 1)[0].strip()
            if header.endswith("."):
                header = header[:-1]
            current_suite = header
            continue
        if current_suite is None:
            continue
        test = raw.strip().split("#", 1)[0].strip()
        if not test:
            continue
        names.append(f"{current_suite}.{test}")
    return names


def find_disabled_tests(output: str) -> list[str]:
    """Return fully-qualified names of DISABLED_ tests in list-tests output.

    A test is disabled if the suite name OR the case name carries the prefix.
    """
    disabled: list[str] = []
    for name in parse_gtest_list_tests(output):
        suite, _, case = name.partition(".")
        if suite.startswith(_DISABLED_PREFIX) or case.startswith(_DISABLED_PREFIX):
            disabled.append(name)
    return disabled


def parse_gtest_xml_skipped(xml_output: str) -> int:
    """Count ``<skipped>`` testcases in a gtest XML report (GTEST_SKIP)."""
    xml_output = _require_str(xml_output, "xml_output")
    if not xml_output.strip():
        return 0
    try:
        root = ElementTree.fromstring(xml_output)
    except ElementTree.ParseError as exc:
        raise ValueError(f"malformed gtest XML output: {exc}") from exc
    # Prefer counting actual <skipped> child elements; fall back to the
    # skipped="" attribute on <testsuites> if no child elements are present.
    skipped_elems = root.findall(".//skipped")
    if skipped_elems:
        return len(skipped_elems)
    attr = root.get("skipped")
    if attr is not None:
        try:
            return int(attr)
        except ValueError as exc:
            raise ValueError(f"non-integer skipped attribute: {attr!r}") from exc
    return 0


def check_disabled_tests_pass(xml_output: str) -> dict:
    """Verify force-run disabled tests all pass (not rot-hiding a failure).

    Runs against the XML produced by
    ``--gtest_filter=*DISABLED_* --gtest_also_run_disabled_tests``.
    A failing disabled test means the code it exercises is broken and the
    subagent merely hid the failure behind the DISABLED_ prefix.
    """
    xml_output = _require_str(xml_output, "xml_output")
    if not xml_output.strip():
        return {"passed": True, "failures": 0, "failed_tests": []}
    try:
        root = ElementTree.fromstring(xml_output)
    except ElementTree.ParseError as exc:
        raise ValueError(f"malformed gtest XML output: {exc}") from exc

    failed_tests: list[str] = []
    for case in root.findall(".//testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            suite = case.get("classname") or case.get("status") or ""
            name = case.get("name", "")
            failed_tests.append(f"{suite}.{name}".strip("."))
    return {
        "passed": len(failed_tests) == 0,
        "failures": len(failed_tests),
        "failed_tests": failed_tests,
    }


def parse_ctest_add_tests(ctest_content: str) -> list[str]:
    """Extract test names from ``add_test(...)`` calls in a CTestTestfile.cmake."""
    ctest_content = _require_str(ctest_content, "ctest_content")
    names: list[str] = []
    # CMake/ctest emits: add_test([=[Suite.Case]=] <cmd> ...)
    # Also handle the plain form: add_test(Suite.Case <cmd> ...)
    bracket = re.findall(r"add_test\(\s*\[=*\[(.+?)\]=*\]", ctest_content)
    names.extend(bracket)
    for m in re.finditer(r"add_test\(\s*([^\[\s\)]+)", ctest_content):
        token = m.group(1)
        if token not in names:
            names.append(token)
    return names


def check_ctest_set_diff(ctest_baseline: str, ctest_current: str) -> dict:
    """Diff the ctest set; fail if any test was removed from the baseline."""
    baseline = set(parse_ctest_add_tests(ctest_baseline))
    current = set(parse_ctest_add_tests(ctest_current))
    removed = sorted(baseline - current)
    added = sorted(current - baseline)
    return {
        "passed": len(removed) == 0,
        "removed": removed,
        "added": added,
    }


def check_test_integrity(
    list_tests_output: str,
    disabled_baseline: list[str],
    *,
    xml_output: str | None = None,
    skipped_baseline: int = 0,
    ctest_baseline: str | None = None,
    ctest_current: str | None = None,
) -> dict:
    """Aggregate C++ test-integrity gate.

    Fails when any of the anti-cheat checks trip:
      * a DISABLED_ test appears that is not in ``disabled_baseline``,
      * ``<skipped>`` count in ``xml_output`` exceeds ``skipped_baseline``,
      * a test was removed from the ctest set.

    Returns a result dict with ``passed`` plus per-check detail.
    """
    list_tests_output = _require_str(list_tests_output, "list_tests_output")
    if not isinstance(disabled_baseline, (list, tuple, set)):
        raise TypeError("disabled_baseline must be a list/tuple/set of test names")
    if not isinstance(skipped_baseline, int) or isinstance(skipped_baseline, bool):
        raise TypeError("skipped_baseline must be an int")
    if skipped_baseline < 0:
        raise ValueError("skipped_baseline must be >= 0")

    baseline_set = set(disabled_baseline)
    disabled = find_disabled_tests(list_tests_output)
    new_disabled = sorted(d for d in disabled if d not in baseline_set)

    result: dict = {
        "disabled_tests": disabled,
        "new_disabled": new_disabled,
        "skipped_count": 0,
        "ctest_removed": [],
        "ctest_added": [],
    }
    passed = len(new_disabled) == 0

    if xml_output is not None:
        skipped = parse_gtest_xml_skipped(xml_output)
        result["skipped_count"] = skipped
        if skipped > skipped_baseline:
            passed = False

    if ctest_baseline is not None or ctest_current is not None:
        diff = check_ctest_set_diff(ctest_baseline or "", ctest_current or "")
        result["ctest_removed"] = diff["removed"]
        result["ctest_added"] = diff["added"]
        if not diff["passed"]:
            passed = False

    result["passed"] = passed
    return result

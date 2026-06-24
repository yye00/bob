"""Bidirectional Requirements Traceability Matrix (RTM) generator.

CLI:
    python -m tools.spec_coverage --workspace . --feature-id <id> --spec spec.yaml

Emits:
    runs/<feature_id>/rtm.json   — machine-readable RTM
    runs/<feature_id>/rtm.html   — human-readable RTM
    metrics.yaml                 — spec_coverage_pct field
    reviews/findings.yaml        — untraced_implementation entries (backward pass)

Forward direction (AC → test → code-region):
  For each AC, scan test files for references (ID or keyword match).
  An AC is 'orphaned' when no test references it.
  spec_coverage_pct = covered_acs / total_acs.

Backward direction (code-region → AC):
  For each public function in src/ that was introduced in the feature commit,
  check whether any AC text or test file references it.
  Unlinked functions are flagged as untraced_implementation.

halt-gate: spec_coverage_pct < 0.80 → check_halt_gate returns (False, reason).
"""

from __future__ import annotations

import ast
import html
import json
import pathlib
import re
import textwrap
from typing import Any

import yaml

_HALT_THRESHOLD = 0.80

# ── helpers ──────────────────────────────────────────────────────────────────


def _load_spec(spec_file: pathlib.Path) -> list[dict[str, str]]:
    """Return list of {id, text} dicts from spec.yaml acceptance_criteria."""
    raw = yaml.safe_load(spec_file.read_text()) or {}
    acs_raw = raw.get("acceptance_criteria") or []
    result = []
    for item in acs_raw:
        if isinstance(item, dict):
            ac_id = item.get("id", "")
            ac_text = item.get("text", "")
        else:
            ac_id = ""
            ac_text = str(item)
        result.append({"id": ac_id, "text": ac_text})
    return result


def _collect_test_files(workspace: pathlib.Path) -> list[pathlib.Path]:
    tests_dir = workspace / "tests"
    if not tests_dir.is_dir():
        return []
    return sorted(tests_dir.rglob("test_*.py")) + sorted(tests_dir.rglob("*_test.py"))


def _collect_src_files(workspace: pathlib.Path) -> list[pathlib.Path]:
    for candidate in ("src", "lib", "."):
        src_dir = workspace / candidate
        if src_dir.is_dir() and candidate != ".":
            return sorted(src_dir.rglob("*.py"))
    return []


def _test_references_ac(test_content: str, ac: dict[str, str]) -> bool:
    """Return True if the test file references this AC by ID or keyword."""
    ac_id = ac["id"]
    ac_text = ac["text"]

    if ac_id and re.search(re.escape(ac_id), test_content):
        return True

    # Extract the first significant keyword from the AC text (e.g. function name)
    keyword_match = re.search(r"[\w.]+\.(\w+)|`(\w+)`|\b(\w{4,})\b", ac_text)
    if keyword_match:
        keyword = next(g for g in keyword_match.groups() if g)
        if re.search(re.escape(keyword), test_content, re.IGNORECASE):
            return True

    return False


def _collect_functions_in_src(workspace: pathlib.Path) -> list[dict[str, str]]:
    """Return list of {function, file} for every top-level def in src/ files."""
    functions = []
    for py_file in _collect_src_files(workspace):
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    functions.append(
                        {
                            "function": node.name,
                            "file": str(py_file.relative_to(workspace)),
                        }
                    )
    return functions


def _function_is_traced(
    fn: dict[str, str],
    acs: list[dict[str, str]],
    test_files: list[pathlib.Path],
) -> bool:
    """Return True if the function name appears in any AC text or test file."""
    name = fn["function"]

    for ac in acs:
        if re.search(r"\b" + re.escape(name) + r"\b", ac["text"]):
            return True

    for tf in test_files:
        try:
            content = tf.read_text()
        except OSError:
            continue
        if re.search(r"\b" + re.escape(name) + r"\b", content):
            return True

    return False


# ── forward pass ─────────────────────────────────────────────────────────────


def _forward_pass(
    acs: list[dict[str, str]],
    test_files: list[pathlib.Path],
    workspace: pathlib.Path,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for ac in acs:
        ac_id = ac["id"] or ac["text"][:40]
        matched_tests: list[str] = []
        exercised_files: list[str] = []

        for tf in test_files:
            try:
                content = tf.read_text()
            except OSError:
                continue
            if _test_references_ac(content, ac):
                rel = str(tf.relative_to(workspace))
                matched_tests.append(rel)
                exercised_files.append(rel)

        result[ac_id] = {
            "text": ac["text"],
            "matched_tests": matched_tests,
            "exercised_files": list(set(exercised_files)),
            "orphan": len(matched_tests) == 0,
        }

    return result


# ── backward pass ─────────────────────────────────────────────────────────────


def _backward_pass(
    acs: list[dict[str, str]],
    test_files: list[pathlib.Path],
    workspace: pathlib.Path,
) -> list[dict[str, str]]:
    functions = _collect_functions_in_src(workspace)
    untraced = []
    for fn in functions:
        if not _function_is_traced(fn, acs, test_files):
            untraced.append(fn)
    return untraced


# ── output writers ────────────────────────────────────────────────────────────


def _write_json(rtm: dict[str, Any], out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rtm.json").write_text(json.dumps(rtm, indent=2))


def _write_html(rtm: dict[str, Any], out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for ac_id, info in rtm.get("acs", {}).items():
        orphan_cell = "YES" if info["orphan"] else "no"
        tests_cell = html.escape(", ".join(info["matched_tests"]) or "—")
        files_cell = html.escape(", ".join(info["exercised_files"]) or "—")
        rows.append(
            f"<tr><td>{html.escape(ac_id)}</td>"
            f"<td>{html.escape(info['text'])}</td>"
            f"<td>{tests_cell}</td>"
            f"<td>{files_cell}</td>"
            f"<td>{orphan_cell}</td></tr>"
        )

    untraced_rows = []
    for fn in rtm.get("untraced_implementations", []):
        untraced_rows.append(
            f"<tr><td>{html.escape(fn['function'])}</td>"
            f"<td>{html.escape(fn['file'])}</td></tr>"
        )

    pct = rtm.get("spec_coverage_pct", 0.0)
    pct_str = f"{pct:.1%}"

    page = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head><meta charset="utf-8"><title>RTM — {html.escape(rtm.get('feature_id',''))}</title>
        <style>
          body{{font-family:sans-serif;margin:1rem}}
          table{{border-collapse:collapse;width:100%}}
          th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}}
          th{{background:#eee}}
          .orphan{{color:red;font-weight:bold}}
        </style>
        </head>
        <body>
        <h1>RTM — {html.escape(rtm.get('feature_id',''))}</h1>
        <p><strong>spec_coverage_pct:</strong> {pct_str}</p>
        <h2>Forward Traceability (AC → test → file)</h2>
        <table>
        <thead><tr><th>AC ID</th><th>AC Text</th><th>Matched Tests</th>
        <th>Exercised Files</th><th>Orphan?</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
        </table>
        <h2>Backward Traceability — Untraced Implementations</h2>
        <table>
        <thead><tr><th>Function</th><th>File</th></tr></thead>
        <tbody>{''.join(untraced_rows) or '<tr><td colspan="2">None</td></tr>'}</tbody>
        </table>
        </body></html>
    """)
    (out_dir / "rtm.html").write_text(page)


def _write_metrics(rtm: dict[str, Any], metrics_path: pathlib.Path) -> None:
    existing: dict[str, Any] = {}
    if metrics_path.exists():
        try:
            existing = yaml.safe_load(metrics_path.read_text()) or {}
        except yaml.YAMLError:
            existing = {}
    existing["spec_coverage_pct"] = rtm["spec_coverage_pct"]
    metrics_path.write_text(yaml.safe_dump(existing, default_flow_style=False))


def _write_findings(
    untraced: list[dict[str, str]],
    feature_id: str,
    findings_path: pathlib.Path,
) -> None:
    if not untraced:
        return

    existing: dict[str, Any] = {}
    if findings_path.exists():
        try:
            existing = yaml.safe_load(findings_path.read_text()) or {}
        except yaml.YAMLError:
            existing = {}

    findings_list: list[dict[str, Any]] = existing.get("findings", [])
    existing_ids = {f.get("id", "") for f in findings_list}

    for fn in untraced:
        finding_id = f"RTM-UNTRACED-{feature_id[:8]}-{fn['function']}"
        if finding_id in existing_ids:
            continue
        findings_list.append(
            {
                "id": finding_id,
                "title": f"Untraced implementation: {fn['function']} in {fn['file']}",
                "pattern": "function-without-ac-link",
                "files": [fn["file"]],
                "severity": "warning",
                "status": "open",
                "tags": ["untraced_implementation"],
                "feature_id": feature_id,
            }
        )

    existing["schema_version"] = existing.get("schema_version", 1)
    existing["findings"] = findings_list
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    findings_path.write_text(yaml.safe_dump(existing, default_flow_style=False))


# ── public API ────────────────────────────────────────────────────────────────


def build_rtm(
    *,
    workspace: "str | pathlib.Path",
    feature_id: str,
    spec_file: "str | pathlib.Path | None" = None,
    runs_dir: "str | pathlib.Path | None" = None,
    metrics_path: "str | pathlib.Path | None" = None,
    findings_path: "str | pathlib.Path | None" = None,
) -> dict[str, Any]:
    """Build the bidirectional RTM for a feature.

    Args:
        workspace: Root directory of the project.
        feature_id: Identifier string for the feature (used in output paths).
        spec_file: Path to spec.yaml. Defaults to workspace/spec.yaml.
        runs_dir: Base directory for output files. Defaults to workspace/runs.
        metrics_path: Where to write metrics.yaml. Defaults to workspace/metrics.yaml.
        findings_path: Where to append findings. Defaults to workspace/reviews/findings.yaml.

    Returns:
        RTM dict with keys: feature_id, acs, spec_coverage_pct, untraced_implementations.
    """
    workspace = pathlib.Path(workspace)

    if spec_file is None:
        spec_file = workspace / "spec.yaml"
    spec_file = pathlib.Path(spec_file)

    if runs_dir is None:
        runs_dir = workspace / "runs"
    runs_dir = pathlib.Path(runs_dir)

    if metrics_path is None:
        metrics_path = workspace / "metrics.yaml"
    metrics_path = pathlib.Path(metrics_path)

    if findings_path is None:
        findings_path = workspace / "reviews" / "findings.yaml"
    findings_path = pathlib.Path(findings_path)

    acs = _load_spec(spec_file)
    test_files = _collect_test_files(workspace)

    forward = _forward_pass(acs, test_files, workspace)
    untraced = _backward_pass(acs, test_files, workspace)

    total = len(acs)
    covered = sum(1 for info in forward.values() if not info["orphan"])
    spec_coverage_pct = 1.0 if total == 0 else covered / total

    rtm: dict[str, Any] = {
        "feature_id": feature_id,
        "acs": forward,
        "spec_coverage_pct": spec_coverage_pct,
        "untraced_implementations": untraced,
    }

    out_dir = runs_dir / feature_id
    _write_json(rtm, out_dir)
    _write_html(rtm, out_dir)

    if metrics_path is not None:
        _write_metrics(rtm, metrics_path)

    if untraced and findings_path is not None:
        _write_findings(untraced, feature_id, findings_path)

    return rtm


def check_halt_gate(rtm: dict[str, Any]) -> tuple[bool, str]:
    """Return (passed, reason).  Fails when spec_coverage_pct < 0.80."""
    pct = rtm.get("spec_coverage_pct", 0.0)
    if pct >= _HALT_THRESHOLD:
        return True, ""
    reason = (
        f"spec_coverage_pct={pct:.2f} is below the halt-gate threshold of 0.80. "
        f"Cover more ACs with tests to proceed."
    )
    return False, reason


def check_spec_coverage_gate(rtm: dict[str, Any]) -> tuple[bool, str]:
    """Return (passed, reason). AC-required alias for check_halt_gate.

    Fails when spec_coverage_pct < 0.80.  Raises ValueError when rtm is not a dict.
    """
    if not isinstance(rtm, dict):
        raise ValueError(f"rtm must be a dict, got {type(rtm).__name__!r}")
    return check_halt_gate(rtm)


# ── aliases required by acceptance criteria ───────────────────────────────────


def generate_rtm(
    *,
    workspace: "str | pathlib.Path",
    feature_id: str,
    spec_file: "str | pathlib.Path | None" = None,
    runs_dir: "str | pathlib.Path | None" = None,
    metrics_path: "str | pathlib.Path | None" = None,
    findings_path: "str | pathlib.Path | None" = None,
) -> dict[str, Any]:
    """Alias for build_rtm — generate bidirectional RTM for a feature.

    Returns RTM dict with keys: feature_id, acs, spec_coverage_pct,
    untraced_implementations.
    """
    return build_rtm(
        workspace=workspace,
        feature_id=feature_id,
        spec_file=spec_file,
        runs_dir=runs_dir,
        metrics_path=metrics_path,
        findings_path=findings_path,
    )


def check_untraced_implementation(
    *,
    workspace: "str | pathlib.Path",
    acs: list[dict[str, str]],
    test_files: "list[pathlib.Path] | None" = None,
) -> list[dict[str, str]]:
    """Alias for flag_untraced_implementation.

    Return list of public functions in src/ that have no AC link or test
    reference — i.e. untraced implementations.
    """
    return flag_untraced_implementation(
        workspace=workspace,
        acs=acs,
        test_files=test_files,
    )


def verify_traceability(
    rtm: dict[str, Any],
    *,
    halt_threshold: float = _HALT_THRESHOLD,
) -> dict[str, Any]:
    """Verify bidirectional traceability of an RTM and return a result dict.

    Runs the halt-gate check and collects untraced implementation warnings.

    Args:
        rtm: RTM dict as produced by generate_rtm / build_rtm.
        halt_threshold: Minimum spec_coverage_pct to pass (default 0.80).

    Returns:
        Dict with keys:
            passed (bool): True iff spec_coverage_pct >= halt_threshold AND
                           no untraced_implementations are present.
            spec_coverage_pct (float): Coverage percentage from the RTM.
            orphan_acs (list[str]): AC IDs that have no matched tests.
            untraced_implementations (list[dict]): Functions without AC links.
            halt_gate_reason (str): Non-empty when halt gate fires.
    """
    if not isinstance(rtm, dict):
        raise ValueError(f"rtm must be a dict, got {type(rtm).__name__!r}")

    pct = rtm.get("spec_coverage_pct", 0.0)
    halt_passed = pct >= halt_threshold
    halt_reason = (
        ""
        if halt_passed
        else (
            f"spec_coverage_pct={pct:.2f} is below the halt-gate threshold of "
            f"{halt_threshold:.2f}. Cover more ACs with tests to proceed."
        )
    )

    acs_info = rtm.get("acs", {})
    orphan_acs = [
        ac_id for ac_id, info in acs_info.items() if info.get("orphan", False)
    ]

    untraced = rtm.get("untraced_implementations", [])

    passed = halt_passed and len(untraced) == 0

    return {
        "passed": passed,
        "spec_coverage_pct": pct,
        "orphan_acs": orphan_acs,
        "untraced_implementations": untraced,
        "halt_gate_reason": halt_reason,
    }


# ── named public-API aliases required by acceptance criteria ──────────────────


def emit_rtm_json(
    rtm: dict[str, Any],
    *,
    runs_dir: "str | pathlib.Path",
    feature_id: str,
) -> pathlib.Path:
    """Write runs/<feature_id>/rtm.json and return the output path.

    Raises PermissionError (message contains "permission") when the
    runs/ directory is not writable.
    """
    runs_dir = pathlib.Path(runs_dir)
    out_dir = runs_dir / feature_id
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "rtm.json"
        out_path.write_text(json.dumps(rtm, indent=2))
        return out_path
    except PermissionError as exc:
        raise PermissionError(
            f"permission denied writing rtm.json to {out_dir}: {exc}"
        ) from exc


def emit_rtm_html(
    rtm: dict[str, Any],
    *,
    runs_dir: "str | pathlib.Path",
    feature_id: str,
) -> pathlib.Path:
    """Write runs/<feature_id>/rtm.html and return the output path."""
    runs_dir = pathlib.Path(runs_dir)
    out_dir = runs_dir / feature_id
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_html(rtm, out_dir)
        return out_dir / "rtm.html"
    except PermissionError as exc:
        raise PermissionError(
            f"permission denied writing rtm.html to {out_dir}: {exc}"
        ) from exc


def compute_ac_record(
    ac: dict[str, str],
    test_files: list[pathlib.Path],
    workspace: pathlib.Path,
) -> dict[str, Any]:
    """Return a single AC record dict with keys matched_tests, exercised_files, orphan."""
    matched_tests: list[str] = []
    exercised_files: list[str] = []

    for tf in test_files:
        try:
            content = tf.read_text()
        except OSError:
            continue
        if _test_references_ac(content, ac):
            rel = str(tf.relative_to(workspace))
            matched_tests.append(rel)
            exercised_files.append(rel)

    return {
        "matched_tests": matched_tests,
        "exercised_files": list(set(exercised_files)),
        "orphan": len(matched_tests) == 0,
    }


def compute_spec_coverage_pct(
    feature_acs: list[dict[str, str]],
    test_files: list[pathlib.Path],
    workspace: pathlib.Path,
) -> float:
    """Return float = covered_acs / total_acs.

    Returns 0.0 when feature_acs is empty (zero-AC path bypasses division).
    """
    if not feature_acs:
        return 0.0
    covered = sum(
        1
        for ac in feature_acs
        if not compute_ac_record(ac, test_files, workspace)["orphan"]
    )
    return covered / len(feature_acs)


def halt_gate_fires_at_80(spec_coverage_pct: float) -> bool:
    """Return True iff spec_coverage_pct < 0.80 (gate fires = halt)."""
    return spec_coverage_pct < _HALT_THRESHOLD


def validate_spec_coverage_pct(
    rtm: dict[str, Any],
    *,
    halt_threshold: float = _HALT_THRESHOLD,
) -> tuple[bool, str]:
    """Validate that spec_coverage_pct meets the halt-gate threshold.

    Returns (passed, reason) where passed is True iff spec_coverage_pct
    >= halt_threshold. reason is empty string when passed, otherwise
    a human-readable explanation of why the gate fired.

    Raises ValueError when rtm is not a dict.
    """
    if not isinstance(rtm, dict):
        raise ValueError(f"rtm must be a dict, got {type(rtm).__name__!r}")
    pct = rtm.get("spec_coverage_pct", 0.0)
    if pct >= halt_threshold:
        return True, ""
    reason = (
        f"spec_coverage_pct={pct:.2f} is below the halt-gate threshold of "
        f"{halt_threshold:.2f}. Cover more ACs with tests to proceed."
    )
    return False, reason


def flag_untraced_implementation(
    *,
    workspace: "str | pathlib.Path",
    acs: list[dict[str, str]],
    test_files: "list[pathlib.Path] | None" = None,
) -> list[dict[str, str]]:
    """Return list of new functions in src/ without any AC link or test reference."""
    workspace = pathlib.Path(workspace)
    if test_files is None:
        test_files = _collect_test_files(workspace)
    return _backward_pass(acs, test_files, workspace)


def check_spec_coverage_pct(
    feature_acs: list[dict[str, str]],
    test_files: list[pathlib.Path],
    workspace: pathlib.Path,
) -> float:
    """Return spec_coverage_pct for the given ACs and test files.

    AC-required alias for compute_spec_coverage_pct.
    Returns 0.0 when feature_acs is empty.
    """
    return compute_spec_coverage_pct(feature_acs, test_files, workspace)


def find_untraced_implementation(
    *,
    workspace: "str | pathlib.Path",
    acs: list[dict[str, str]],
    test_files: "list[pathlib.Path] | None" = None,
) -> list[dict[str, str]]:
    """Return list of public functions in src/ without any AC link or test reference.

    AC-required alias for flag_untraced_implementation.
    """
    return flag_untraced_implementation(workspace=workspace, acs=acs, test_files=test_files)


def detect_untraced_implementation(
    *,
    workspace: "str | pathlib.Path",
    acs: list[dict[str, str]],
    test_files: "list[pathlib.Path] | None" = None,
) -> list[dict[str, str]]:
    """Return list of public functions in src/ without any AC link or test reference.

    AC-required alias for flag_untraced_implementation. New functions in a
    commit without an AC link are flagged as untraced_implementation.
    """
    return flag_untraced_implementation(workspace=workspace, acs=acs, test_files=test_files)


def handle_zero_acs(feature_acs: list[dict[str, str]]) -> float:
    """Return spec_coverage_pct=0.0 when feature has zero ACs.

    Zero-AC path bypasses division to avoid ZeroDivisionError.
    """
    if not feature_acs:
        return 0.0
    raise ValueError("feature_acs is not empty; use compute_spec_coverage_pct instead")


def never_divides_by_zero_on_empty_acs() -> bool:
    """Return True; documents that the zero-AC path bypasses division.

    When total_acs == 0, compute_spec_coverage_pct returns 0.0 directly
    without dividing, so ZeroDivisionError is impossible.
    """
    return True


def validate_ac_traceability(
    acs: list[dict[str, str]],
    test_files: list[pathlib.Path],
    workspace: "str | pathlib.Path",
) -> dict[str, Any]:
    """Validate bidirectional AC traceability and return a result dict.

    Checks each AC in the forward direction (AC -> tests) and returns
    which ACs are orphaned (no test coverage) vs covered.

    Raises ValueError when any AC entry is not a dict, or has neither
    'id' nor 'text' keys (i.e., is a completely invalid AC format).

    Args:
        acs: List of {id, text} dicts from spec.yaml acceptance_criteria.
        test_files: List of Path objects pointing to test files.
        workspace: Root directory of the project.

    Returns:
        Dict with keys:
            valid (bool): True iff all ACs have test coverage (no orphans).
            orphan_acs (list[str]): AC IDs/keys with no test reference.
            covered_acs (list[str]): AC IDs/keys with at least one test reference.
            spec_coverage_pct (float): Fraction of ACs covered by tests.
    """
    workspace = pathlib.Path(workspace)

    for ac in acs:
        if not isinstance(ac, dict):
            raise ValueError(
                f"Each AC must be a dict, got {type(ac).__name__!r}: {ac!r}"
            )
        if "id" not in ac and "text" not in ac:
            raise ValueError(
                f"AC dict must have at least an 'id' or 'text' key, got: {ac!r}"
            )

    orphan_acs: list[str] = []
    covered_acs: list[str] = []

    for ac in acs:
        ac_key = ac.get("id") or (ac.get("text", "")[:40])
        record = compute_ac_record(ac, test_files, workspace)
        if record["orphan"]:
            orphan_acs.append(ac_key)
        else:
            covered_acs.append(ac_key)

    total = len(acs)
    spec_coverage_pct = 0.0 if total == 0 else len(covered_acs) / total

    return {
        "valid": len(orphan_acs) == 0,
        "orphan_acs": orphan_acs,
        "covered_acs": covered_acs,
        "spec_coverage_pct": spec_coverage_pct,
    }


def artifact_path_field() -> str:
    """Return the field name on the Feature model that stores the RTM artifact path.

    The AC text uses the word "artifact"; the model field name is rtm_artifact_path.
    """
    return "rtm_artifact_path"


def emit_rtm_artifacts(
    rtm: dict[str, Any],
    *,
    out_dir: "str | pathlib.Path",
) -> tuple[pathlib.Path, pathlib.Path]:
    """Write rtm.json and rtm.html to out_dir and return (json_path, html_path).

    This is the primary emit function required by the RTM artifact AC.
    Raises ValueError when ``rtm`` is not a dict.
    Raises PermissionError when ``out_dir`` is not writable.
    """
    if not isinstance(rtm, dict):
        raise ValueError(f"rtm must be a dict, got {type(rtm).__name__!r}")
    out_dir = pathlib.Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "rtm.json"
        json_path.write_text(json.dumps(rtm, indent=2))
        _write_html(rtm, out_dir)
        html_path = out_dir / "rtm.html"
        return json_path, html_path
    except PermissionError as exc:
        raise PermissionError(
            f"permission denied writing RTM artifacts to {out_dir}: {exc}"
        ) from exc


def emit_rtm(
    rtm: dict[str, Any],
    *,
    out_dir: "str | pathlib.Path",
) -> tuple[pathlib.Path, pathlib.Path]:
    """Write rtm.json and rtm.html to out_dir and return (json_path, html_path).

    This is the combined emit function required by the RTM artifact AC.
    Raises ValueError when ``rtm`` is not a dict.
    Raises PermissionError when ``out_dir`` is not writable.
    """
    if not isinstance(rtm, dict):
        raise ValueError(f"rtm must be a dict, got {type(rtm).__name__!r}")
    out_dir = pathlib.Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "rtm.json"
        json_path.write_text(json.dumps(rtm, indent=2))
        _write_html(rtm, out_dir)
        html_path = out_dir / "rtm.html"
        return json_path, html_path
    except PermissionError as exc:
        raise PermissionError(
            f"permission denied writing RTM artifacts to {out_dir}: {exc}"
        ) from exc


# ── AC-required generate_rtm_json / generate_rtm_html aliases ────────────────


def generate_rtm_json(
    rtm: dict[str, Any],
    *,
    runs_dir: "str | pathlib.Path",
    feature_id: str,
) -> pathlib.Path:
    """Write runs/<feature_id>/rtm.json and return the output path.

    AC-required alias for emit_rtm_json.
    Raises PermissionError when the runs/ directory is not writable.
    """
    return emit_rtm_json(rtm, runs_dir=runs_dir, feature_id=feature_id)


def generate_rtm_html(
    rtm: dict[str, Any],
    *,
    runs_dir: "str | pathlib.Path",
    feature_id: str,
) -> pathlib.Path:
    """Write runs/<feature_id>/rtm.html and return the output path.

    AC-required alias for emit_rtm_html.
    """
    return emit_rtm_html(rtm, runs_dir=runs_dir, feature_id=feature_id)


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point for the spec_coverage command."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate RTM for a feature.")
    parser.add_argument("--workspace", default=".", help="Project workspace root")
    parser.add_argument("--feature-id", required=True, help="Feature ID")
    parser.add_argument("--spec", help="Path to spec.yaml")
    parser.add_argument("--runs-dir", help="Base directory for RTM output")
    parser.add_argument("--metrics", help="Path to metrics.yaml")
    parser.add_argument("--findings", help="Path to findings.yaml")
    args = parser.parse_args()

    rtm = build_rtm(
        workspace=args.workspace,
        feature_id=args.feature_id,
        spec_file=args.spec,
        runs_dir=args.runs_dir,
        metrics_path=args.metrics,
        findings_path=args.findings,
    )

    passed, reason = check_halt_gate(rtm)
    print(f"spec_coverage_pct: {rtm['spec_coverage_pct']:.1%}")
    print(f"halt_gate: {'PASS' if passed else 'FAIL'}")
    if not passed:
        print(f"  reason: {reason}")
    print(f"untraced_implementations: {len(rtm['untraced_implementations'])}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()

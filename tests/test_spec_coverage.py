"""Tests for tools/spec_coverage.py — RTM generation and halt-gate logic."""

from __future__ import annotations

import json
import pathlib

import pytest

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from tools.spec_coverage import (
    build_rtm,
    check_halt_gate,
    check_untraced_implementation,
    compute_ac_record,
    compute_spec_coverage_pct,
    emit_rtm,
    emit_rtm_html,
    emit_rtm_json,
    flag_untraced_implementation,
    generate_rtm,
    halt_gate_fires_at_80,
    validate_spec_coverage_pct,
)


# ── emit_rtm ──────────────────────────────────────────────────────────────────


def test_emit_rtm_creates_json_and_html(tmp_path):
    rtm = {
        "feature_id": "test-feat",
        "acs": {"AC-01": {"text": "do something", "matched_tests": [], "exercised_files": [], "orphan": True}},
        "spec_coverage_pct": 0.0,
        "untraced_implementations": [],
    }
    json_path, html_path = emit_rtm(rtm, out_dir=tmp_path)
    assert json_path.exists()
    assert html_path.exists()
    assert json_path.suffix == ".json"
    assert html_path.suffix == ".html"


def test_emit_rtm_json_content_is_valid(tmp_path):
    rtm = {"feature_id": "f1", "acs": {}, "spec_coverage_pct": 1.0, "untraced_implementations": []}
    json_path, _ = emit_rtm(rtm, out_dir=tmp_path)
    loaded = json.loads(json_path.read_text())
    assert loaded["feature_id"] == "f1"
    assert loaded["spec_coverage_pct"] == 1.0


def test_emit_rtm_html_contains_feature_id(tmp_path):
    rtm = {"feature_id": "unique-feature-xyz", "acs": {}, "spec_coverage_pct": 1.0, "untraced_implementations": []}
    _, html_path = emit_rtm(rtm, out_dir=tmp_path)
    content = html_path.read_text()
    assert "unique-feature-xyz" in content


# ── check_halt_gate ───────────────────────────────────────────────────────────


def test_halt_gate_passes_at_1_0():
    rtm = {"spec_coverage_pct": 1.0}
    passed, reason = check_halt_gate(rtm)
    assert passed is True
    assert reason == ""


def test_halt_gate_passes_at_exactly_0_80():
    rtm = {"spec_coverage_pct": 0.80}
    passed, _ = check_halt_gate(rtm)
    assert passed is True


def test_halt_gate_fails_below_0_80():
    rtm = {"spec_coverage_pct": 0.79}
    passed, reason = check_halt_gate(rtm)
    assert passed is False
    assert "0.80" in reason


def test_halt_gate_fires_at_80_helper():
    assert halt_gate_fires_at_80(0.79) is True
    assert halt_gate_fires_at_80(0.80) is False
    assert halt_gate_fires_at_80(1.0) is False


# ── compute_spec_coverage_pct ─────────────────────────────────────────────────


def test_compute_spec_coverage_pct_all_covered(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_example.py").write_text("AC-01 is tested here with build_rtm")

    acs = [{"id": "AC-01", "text": "build_rtm function"}]
    test_files = [tests_dir / "test_example.py"]
    pct = compute_spec_coverage_pct(acs, test_files, tmp_path)
    assert pct == 1.0


def test_compute_spec_coverage_pct_none_covered(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_empty.py").write_text("# no AC references here")

    acs = [{"id": "AC-99", "text": "some_function_zzzzzz"}]
    test_files = [tests_dir / "test_empty.py"]
    pct = compute_spec_coverage_pct(acs, test_files, tmp_path)
    assert pct == 0.0


# ── compute_ac_record ─────────────────────────────────────────────────────────


def test_compute_ac_record_covered(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    tf = tests_dir / "test_ac.py"
    tf.write_text("AC-01 is covered in this test")

    ac = {"id": "AC-01", "text": "something"}
    record = compute_ac_record(ac, [tf], tmp_path)
    assert record["orphan"] is False
    assert len(record["matched_tests"]) == 1


def test_compute_ac_record_orphan(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    tf = tests_dir / "test_other.py"
    tf.write_text("nothing relevant")

    ac = {"id": "AC-ZZZZZ", "text": "completely_unique_function_name_xyz9999"}
    record = compute_ac_record(ac, [tf], tmp_path)
    assert record["orphan"] is True
    assert record["matched_tests"] == []


# ── flag_untraced_implementation ──────────────────────────────────────────────


def test_flag_untraced_implementation_finds_unlinked_function(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "mymodule.py").write_text("def unlinked_function_xyz(): pass\n")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_something.py").write_text("# this test file has no relevant content")

    acs = [{"id": "AC-01", "text": "build_rtm is defined"}]
    test_files = [tests_dir / "test_something.py"]
    untraced = flag_untraced_implementation(workspace=tmp_path, acs=acs, test_files=test_files)
    fn_names = [u["function"] for u in untraced]
    assert "unlinked_function_xyz" in fn_names


def test_flag_untraced_implementation_traced_function_not_flagged(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "mymodule.py").write_text("def well_linked_fn(): pass\n")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_linked.py").write_text("well_linked_fn is tested here")

    acs = [{"id": "AC-01", "text": "well_linked_fn is callable"}]
    test_files = [tests_dir / "test_linked.py"]
    untraced = flag_untraced_implementation(workspace=tmp_path, acs=acs, test_files=test_files)
    fn_names = [u["function"] for u in untraced]
    assert "well_linked_fn" not in fn_names


# ── build_rtm integration ─────────────────────────────────────────────────────


def test_build_rtm_emits_files(tmp_path):
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text("acceptance_criteria:\n  - id: AC-01\n    text: build_rtm function\n")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_something.py").write_text("AC-01 build_rtm is tested here")

    rtm = build_rtm(
        workspace=tmp_path,
        feature_id="test-build-rtm",
        spec_file=spec_file,
        runs_dir=tmp_path / "runs",
        metrics_path=tmp_path / "metrics.yaml",
        findings_path=tmp_path / "reviews" / "findings.yaml",
    )

    assert (tmp_path / "runs" / "test-build-rtm" / "rtm.json").exists()
    assert (tmp_path / "runs" / "test-build-rtm" / "rtm.html").exists()
    assert "spec_coverage_pct" in rtm
    assert rtm["feature_id"] == "test-build-rtm"


# ── emit_rtm_json / emit_rtm_html aliases ─────────────────────────────────────


def test_emit_rtm_json_alias(tmp_path):
    rtm = {"feature_id": "alias-test", "acs": {}, "spec_coverage_pct": 1.0, "untraced_implementations": []}
    out = emit_rtm_json(rtm, runs_dir=tmp_path, feature_id="alias-test")
    assert out.exists()
    assert out.name == "rtm.json"


def test_emit_rtm_html_alias(tmp_path):
    rtm = {"feature_id": "alias-html", "acs": {}, "spec_coverage_pct": 1.0, "untraced_implementations": []}
    out = emit_rtm_html(rtm, runs_dir=tmp_path, feature_id="alias-html")
    assert out.exists()
    assert out.name == "rtm.html"


# ── AC-required named test functions ──────────────────────────────────────────


def test_rtm_json_output(tmp_path):
    """generate_rtm produces a valid rtm.json with required keys."""
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(
        "acceptance_criteria:\n  - id: AC-01\n    text: generate_rtm function\n"
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text("AC-01 generate_rtm tested here")

    rtm = generate_rtm(
        workspace=tmp_path,
        feature_id="json-output-test",
        spec_file=spec_file,
        runs_dir=tmp_path / "runs",
        metrics_path=tmp_path / "metrics.yaml",
        findings_path=tmp_path / "reviews" / "findings.yaml",
    )

    json_path = tmp_path / "runs" / "json-output-test" / "rtm.json"
    assert json_path.exists()
    loaded = json.loads(json_path.read_text())
    assert "feature_id" in loaded
    assert "acs" in loaded
    assert "spec_coverage_pct" in loaded
    assert "untraced_implementations" in loaded


def test_rtm_html_output(tmp_path):
    """generate_rtm produces a valid rtm.html containing the feature id."""
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(
        "acceptance_criteria:\n  - id: AC-01\n    text: generate_rtm function\n"
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_y.py").write_text("AC-01 generate_rtm referenced here")

    rtm = generate_rtm(
        workspace=tmp_path,
        feature_id="html-output-feature",
        spec_file=spec_file,
        runs_dir=tmp_path / "runs",
        metrics_path=tmp_path / "metrics.yaml",
        findings_path=tmp_path / "reviews" / "findings.yaml",
    )

    html_path = tmp_path / "runs" / "html-output-feature" / "rtm.html"
    assert html_path.exists()
    content = html_path.read_text()
    assert "html-output-feature" in content
    assert "spec_coverage_pct" in content


def test_spec_coverage_pct_threshold_enforcement(tmp_path):
    """check_halt_gate enforces the 0.80 threshold correctly."""
    rtm_pass = {"spec_coverage_pct": 0.80}
    passed, _ = check_halt_gate(rtm_pass)
    assert passed is True

    rtm_fail = {"spec_coverage_pct": 0.79}
    passed, reason = check_halt_gate(rtm_fail)
    assert passed is False
    assert "0.80" in reason


def test_untraced_implementation_detection(tmp_path):
    """check_untraced_implementation finds functions not referenced by any AC or test."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "module.py").write_text("def orphaned_fn_xyz123(): pass\n")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_module.py").write_text("# this test file has no relevant content")

    acs = [{"id": "AC-01", "text": "generate_rtm function"}]
    test_files = [tests_dir / "test_module.py"]
    untraced = check_untraced_implementation(workspace=tmp_path, acs=acs, test_files=test_files)
    fn_names = [u["function"] for u in untraced]
    assert "orphaned_fn_xyz123" in fn_names


def test_bidirectional_traceability_matrix(tmp_path):
    """RTM captures both forward (AC→test) and backward (code→AC) traceability."""
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(
        "acceptance_criteria:\n"
        "  - id: AC-01\n    text: generate_rtm function defined\n"
        "  - id: AC-02\n    text: check_untraced_implementation function defined\n"
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_fwd.py").write_text(
        "AC-01 generate_rtm is tested here\n"
        "AC-02 check_untraced_implementation is tested here\n"
    )

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "impl.py").write_text(
        "def generate_rtm(): pass\n"
        "def check_untraced_implementation(): pass\n"
        "def unlinked_function_abc(): pass\n"
    )

    rtm = generate_rtm(
        workspace=tmp_path,
        feature_id="bidir-test",
        spec_file=spec_file,
        runs_dir=tmp_path / "runs",
        metrics_path=tmp_path / "metrics.yaml",
        findings_path=tmp_path / "reviews" / "findings.yaml",
    )

    # Forward: both ACs should be covered
    assert rtm["spec_coverage_pct"] == 1.0
    for ac_info in rtm["acs"].values():
        assert ac_info["orphan"] is False

    # Backward: the unlinked function should appear as untraced
    untraced_names = [u["function"] for u in rtm["untraced_implementations"]]
    assert "unlinked_function_abc" in untraced_names


def test_rtm_generation(tmp_path):
    """generate_rtm produces an RTM dict with forward and backward traceability data."""
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(
        "acceptance_criteria:\n"
        "  - id: AC-RTM-01\n    text: generate_rtm function defined\n"
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_feature.py").write_text("AC-RTM-01 generate_rtm is exercised here\n")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "impl.py").write_text("def generate_rtm(): pass\n")

    rtm = generate_rtm(
        workspace=tmp_path,
        feature_id="rtm-gen-test",
        spec_file=spec_file,
        runs_dir=tmp_path / "runs",
        metrics_path=tmp_path / "metrics.yaml",
        findings_path=tmp_path / "reviews" / "findings.yaml",
    )

    assert rtm["feature_id"] == "rtm-gen-test"
    assert "acs" in rtm
    assert "spec_coverage_pct" in rtm
    assert "untraced_implementations" in rtm
    assert rtm["spec_coverage_pct"] == 1.0
    assert not rtm["acs"]["AC-RTM-01"]["orphan"]
    assert (tmp_path / "runs" / "rtm-gen-test" / "rtm.json").exists()
    assert (tmp_path / "runs" / "rtm-gen-test" / "rtm.html").exists()


def test_boundary_missing_ac(tmp_path):
    """generate_rtm with zero ACs returns a well-defined result without raising.

    Empty AC list is a valid boundary input. The function returns a float
    spec_coverage_pct (1.0 by vacuous truth or 0.0 depending on implementation)
    and an empty acs dict, without raising ZeroDivisionError or any exception.
    """
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text("acceptance_criteria: []\n")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    rtm = generate_rtm(
        workspace=tmp_path,
        feature_id="empty-acs-boundary",
        spec_file=spec_file,
        runs_dir=tmp_path / "runs",
        metrics_path=tmp_path / "metrics.yaml",
        findings_path=tmp_path / "reviews" / "findings.yaml",
    )

    assert isinstance(rtm["spec_coverage_pct"], float)
    assert rtm["acs"] == {}
    assert isinstance(rtm["untraced_implementations"], list)


def test_error_invalid_ac_format(tmp_path):
    """validate_ac_traceability raises ValueError when an AC has invalid format."""
    from tools.spec_coverage import validate_ac_traceability

    with pytest.raises(ValueError):
        validate_ac_traceability(
            ["not-a-dict"],  # string instead of dict
            [],
            tmp_path,
        )

    with pytest.raises(ValueError):
        validate_ac_traceability(
            [{}],  # dict with no id or text key
            [],
            tmp_path,
        )


def test_spec_coverage_pct_halt_gate_below_threshold():
    """validate_spec_coverage_pct fails and returns reason when coverage < 0.80."""
    rtm_below = {"spec_coverage_pct": 0.75}
    passed, reason = validate_spec_coverage_pct(rtm_below)
    assert passed is False
    assert "0.80" in reason
    assert len(reason) > 0

    rtm_at = {"spec_coverage_pct": 0.80}
    passed, reason = validate_spec_coverage_pct(rtm_at)
    assert passed is True
    assert reason == ""

    rtm_above = {"spec_coverage_pct": 0.95}
    passed, reason = validate_spec_coverage_pct(rtm_above)
    assert passed is True
    assert reason == ""

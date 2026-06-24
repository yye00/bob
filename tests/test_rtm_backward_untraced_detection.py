"""Tests for backward traceability: new functions without an AC link are flagged."""

from __future__ import annotations

import pathlib

import pytest


@pytest.fixture()
def tmp_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "acceptance_criteria:\n"
        "  - id: AC-01\n"
        "    text: 'Function defined: mymodule.traced_fn'\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "mymodule.py").write_text(
        "def traced_fn():\n"
        "    pass\n"
        "\n"
        "def untraced_fn():\n"
        "    pass\n"
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_mod.py").write_text(
        "# AC-01\n"
        "def test_traced():\n"
        "    assert True\n"
    )
    return tmp_path


def test_backward_untraced_function_flagged(tmp_workspace):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-back",
        spec_file=tmp_workspace / "spec.yaml",
    )

    untraced = rtm.get("untraced_implementations", [])
    names = [u["function"] for u in untraced]
    assert "untraced_fn" in names


def test_backward_traced_function_not_flagged(tmp_workspace):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-back2",
        spec_file=tmp_workspace / "spec.yaml",
    )

    untraced = rtm.get("untraced_implementations", [])
    names = [u["function"] for u in untraced]
    assert "traced_fn" not in names


def test_backward_untraced_finding_has_required_fields(tmp_workspace):
    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-back3",
        spec_file=tmp_workspace / "spec.yaml",
    )

    untraced = rtm.get("untraced_implementations", [])
    assert len(untraced) >= 1
    item = next(u for u in untraced if u["function"] == "untraced_fn")
    assert "file" in item
    assert "function" in item


def test_backward_untraced_written_to_findings_yaml(tmp_workspace):
    """Backward pass must append untraced_implementation entries to findings.yaml."""
    import yaml  # type: ignore

    from tools.spec_coverage import build_rtm

    findings_path = tmp_workspace / "reviews" / "findings.yaml"
    (tmp_workspace / "reviews").mkdir()
    findings_path.write_text("schema_version: 1\nfindings: []\n")

    build_rtm(
        workspace=tmp_workspace,
        feature_id="feat-back4",
        spec_file=tmp_workspace / "spec.yaml",
        findings_path=findings_path,
    )

    data = yaml.safe_load(findings_path.read_text())
    tags = [tag for f in data["findings"] for tag in f.get("tags", [])]
    assert "untraced_implementation" in tags


def test_backward_no_findings_when_all_traced(tmp_path):
    """If every function maps to an AC, no untraced entries emitted."""
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "acceptance_criteria:\n"
        "  - id: AC-01\n"
        "    text: 'Function defined: mymod.only_fn'\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "mymod.py").write_text("def only_fn():\n    pass\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_only.py").write_text(
        "# AC-01\ndef test_x(): assert True\n"
    )

    from tools.spec_coverage import build_rtm

    rtm = build_rtm(
        workspace=tmp_path,
        feature_id="feat-all-traced",
        spec_file=tmp_path / "spec.yaml",
    )

    assert rtm.get("untraced_implementations", []) == []

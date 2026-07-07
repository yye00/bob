"""Tests for the structural-AC fuzzy function-lookup fallback (e76fdbbe).

Feature: when a structural AC of the form "module src/bob/X.py defines
function Y" fails the exact-module lookup because Y actually landed in a
different module (src/bob/Z.py), fuzzy_function_lookup / verify_structural_ac
grep the workspace for `def Y(` (or `class Y`), and on a hit demote to a
WARNING + PASS rather than hard-failing. On a true miss they still fail.
"""

from __future__ import annotations

import pathlib

import pytest

from bob.enhanced_verification import fuzzy_function_lookup, verify_structural_ac


def _make_workspace(
    tmp_path: pathlib.Path,
    *,
    src_files: dict[str, str] | None = None,
) -> pathlib.Path:
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    for rel_path, content in (src_files or {}).items():
        full = tmp_path / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    reviews = tmp_path / "reviews"
    reviews.mkdir(exist_ok=True)
    (reviews / "findings.yaml").write_text("schema_version: 1\nfindings: []\n")
    return tmp_path


def test_fuzzy_lookup_passes_when_function_in_other_module(tmp_path):
    ws = _make_workspace(
        tmp_path,
        src_files={"src/bob/Z.py": "def function_in_z(arg):\n    return arg\n"},
    )
    assert fuzzy_function_lookup(
        workspace=ws,
        symbol_name="function_in_z",
        expected_module_path="bob.X",
    ) is True


def test_fuzzy_lookup_fails_when_truly_absent(tmp_path):
    ws = _make_workspace(tmp_path, src_files={"src/bob/Z.py": "x = 1\n"})
    assert fuzzy_function_lookup(
        workspace=ws,
        symbol_name="nonexistent_symbol",
        expected_module_path="bob.X",
    ) is False


def test_fuzzy_lookup_finds_class(tmp_path):
    ws = _make_workspace(
        tmp_path,
        src_files={"src/bob/Z.py": "class WidgetInZ:\n    pass\n"},
    )
    assert fuzzy_function_lookup(
        workspace=ws,
        symbol_name="WidgetInZ",
        expected_module_path="bob.X",
        is_class=True,
    ) is True


def test_fuzzy_lookup_emits_warning_on_hit(tmp_path):
    findings = tmp_path / "reviews" / "findings.yaml"
    ws = _make_workspace(
        tmp_path,
        src_files={"src/bob/Z.py": "def function_in_z(arg):\n    return arg\n"},
    )
    assert fuzzy_function_lookup(
        workspace=ws,
        symbol_name="function_in_z",
        expected_module_path="bob.X",
        findings_path=findings,
    ) is True
    # A warning record should be recorded on the demotion path.
    assert findings.exists()
    assert "function_in_z" in findings.read_text()


def test_verify_structural_ac_function_defined_via_fuzzy(tmp_path):
    ws = _make_workspace(
        tmp_path,
        src_files={"src/bob/Z.py": "def function_in_z(arg):\n    return arg\n"},
    )
    passed, reason = verify_structural_ac(
        "Function defined: bob.X.function_in_z",
        workspace=ws,
    )
    assert passed is True
    assert "function_in_z" in reason


def test_verify_structural_ac_hard_fails_when_absent(tmp_path):
    ws = _make_workspace(tmp_path, src_files={"src/bob/Z.py": "x = 1\n"})
    passed, _reason = verify_structural_ac(
        "Function defined: bob.X.totally_missing",
        workspace=ws,
    )
    assert passed is False


def test_verify_structural_ac_file_exists(tmp_path):
    ws = _make_workspace(tmp_path, src_files={"src/bob/Z.py": "x = 1\n"})
    passed, _reason = verify_structural_ac("File exists: src/bob/Z.py", workspace=ws)
    assert passed is True


def test_verify_structural_ac_rejects_empty_criterion():
    with pytest.raises(ValueError):
        verify_structural_ac("")


def test_fuzzy_lookup_rejects_empty_symbol(tmp_path):
    with pytest.raises(ValueError):
        fuzzy_function_lookup(
            workspace=tmp_path,
            symbol_name="",
            expected_module_path="bob.X",
        )

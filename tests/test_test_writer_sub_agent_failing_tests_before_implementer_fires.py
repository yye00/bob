"""Tests for test_writer_sub_agent_failing_tests_before_implementer_fires."""

from __future__ import annotations

from pathlib import Path

import pytest

import bob.test_writer_sub_agent_failing_tests_before_implementer_fires as _mod
from bob.orchestrator.test_writer_agent import (
    BijectionReport,
    EmittedTest,
    FilterResult,
)

_run = _mod.test_writer_sub_agent_failing_tests_before_implementer_fires


def test_test_writer_sub_agent_failing_tests_before_implementer_fires(tmp_path):
    """Primary AC test: emits failing tests, applies triple filter, checks bijection."""
    acs = [
        "File exists: src/bob/mymod.py",
        "Function defined: bob.mymod.my_fn",
    ]
    result = _run(
        "feat-primary",
        acs,
        workspace=tmp_path,
    )

    assert "emitted" in result
    assert "filter_results" in result
    assert "bijection" in result
    assert "gate_passed" in result

    assert len(result["emitted"]) == 2
    assert len(result["filter_results"]) == 2

    assert all(isinstance(e, EmittedTest) for e in result["emitted"])
    assert all(isinstance(r, FilterResult) for r in result["filter_results"])
    assert isinstance(result["bijection"], BijectionReport)

    assert isinstance(result["gate_passed"], bool)
    assert result["gate_passed"] is True
    assert result["bijection"].is_bijective is True


class TestTestWriterSubAgentEmits:
    def test_emits_one_file_per_ac(self, tmp_path):
        acs = ["File exists: src/a.py", "pytest: tests/test_b.py", "Function defined: bob.c.fn"]
        result = _run(
            "feat-emit-count", acs, workspace=tmp_path
        )
        assert len(result["emitted"]) == 3

    def test_test_files_exist_on_disk(self, tmp_path):
        acs = ["File exists: src/mod.py"]
        result = _run(
            "feat-disk", acs, workspace=tmp_path
        )
        for e in result["emitted"]:
            assert e.test_path.exists()

    def test_empty_acs_produces_empty_result(self, tmp_path):
        result = _run(
            "feat-empty", [], workspace=tmp_path
        )
        assert result["emitted"] == []
        assert result["filter_results"] == []
        assert result["gate_passed"] is True
        assert result["bijection"].is_bijective is True

    def test_init_py_created_in_output_dir(self, tmp_path):
        acs = ["File exists: src/init_test.py"]
        test_writer_sub_agent_failing_tests_before_implementer_fires(
            "feat-init", acs, workspace=tmp_path
        )
        init = tmp_path / "tests" / "feat-init" / "__init__.py"
        assert init.exists()

    def test_emitted_test_has_correct_feature_id(self, tmp_path):
        acs = ["Function defined: bob.x.y"]
        result = _run(
            "feat-fid-check", acs, workspace=tmp_path
        )
        assert result["emitted"][0].feature_id == "feat-fid-check"


class TestTestWriterSubAgentFilter:
    def test_all_emitted_tests_accepted_by_triple_filter(self, tmp_path):
        acs = ["File exists: src/bob/core.py", "pytest: tests/test_core.py"]
        result = _run(
            "feat-filter", acs, workspace=tmp_path
        )
        assert all(r.accepted for r in result["filter_results"])

    def test_filter_results_count_matches_emitted(self, tmp_path):
        acs = ["File exists: src/x.py", "Function defined: bob.x.run"]
        result = _run(
            "feat-filter-count", acs, workspace=tmp_path
        )
        assert len(result["filter_results"]) == len(result["emitted"])

    def test_gate_passed_false_when_bijection_broken(self, tmp_path):
        acs = ["File exists: src/gap.py"]
        result = _run(
            "feat-gate-broken", acs, workspace=tmp_path
        )
        # Manually remove a test to break bijection
        for e in result["emitted"]:
            e.test_path.unlink()

        from bob.orchestrator.test_writer_agent import verify_bijection
        broken_bijection = verify_bijection("feat-gate-broken", acs, workspace=tmp_path)
        assert broken_bijection.is_bijective is False


class TestTestWriterSubAgentBijection:
    def test_bijection_satisfied_after_emit(self, tmp_path):
        acs = ["File exists: src/bij.py", "Function defined: bob.bij.fn"]
        result = _run(
            "feat-bij", acs, workspace=tmp_path
        )
        assert result["bijection"].is_bijective is True
        assert result["bijection"].missing_tests == []
        assert result["bijection"].orphan_tests == []

    def test_bijection_has_correct_ac_ids_count(self, tmp_path):
        acs = ["File exists: src/a.py", "pytest: tests/test_a.py", "Function defined: bob.a.fn"]
        result = _run(
            "feat-bij-ids", acs, workspace=tmp_path
        )
        assert len(result["bijection"].ac_ids) == 3


class TestTestWriterSubAgentWorkspace:
    def test_uses_cwd_when_no_workspace(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        acs = ["File exists: src/default.py"]
        result = _run(
            "feat-cwd", acs
        )
        expected = tmp_path / "tests" / "feat-cwd"
        assert expected.exists()
        assert result["emitted"][0].test_path.parent == expected

    def test_accepts_string_workspace(self, tmp_path):
        acs = ["Function defined: bob.strws.fn"]
        result = _run(
            "feat-strws", acs, workspace=str(tmp_path)
        )
        assert len(result["emitted"]) == 1
        assert result["emitted"][0].test_path.exists()

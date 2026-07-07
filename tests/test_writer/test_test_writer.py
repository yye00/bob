"""Tests for bob.test_writer public API.

Covers the four functions required by feature 711f8a58-ff5a-4474-b379-e5997095bdaf:
  - generate_failing_tests
  - filter_by_compilation
  - filter_by_stub_pass
  - filter_by_coverage
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from bob.test_writer import (
    EmittedTest,
    build_pass_coverage_filter,
    filter_by_compilation,
    filter_by_coverage,
    filter_by_stub_pass,
    generate_failing_tests,
)


class TestGenerateFailingTests:
    def test_returns_dict_with_expected_keys(self, tmp_path):
        result = generate_failing_tests(
            "feat-tw-keys",
            ["File exists: src/mod.py"],
            workspace=tmp_path,
        )
        assert isinstance(result, dict)
        for key in ("emitted", "filter_results", "bijection", "gate_passed"):
            assert key in result, f"Missing key: {key}"

    def test_one_emitted_test_per_ac(self, tmp_path):
        acs = ["File exists: src/a.py", "File exists: src/b.py"]
        result = generate_failing_tests("feat-tw-count", acs, workspace=tmp_path)
        assert len(result["emitted"]) == len(acs)

    def test_empty_ac_list_returns_empty_emitted(self, tmp_path):
        result = generate_failing_tests("feat-tw-empty", [], workspace=tmp_path)
        assert result["emitted"] == []
        assert result["gate_passed"] is True

    def test_test_files_exist_on_disk(self, tmp_path):
        acs = ["File exists: src/x.py"]
        result = generate_failing_tests("feat-tw-exists", acs, workspace=tmp_path)
        for et in result["emitted"]:
            assert et.test_path.exists()

    def test_test_files_are_non_empty_python(self, tmp_path):
        acs = ["File exists: src/x.py"]
        result = generate_failing_tests("feat-tw-red", acs, workspace=tmp_path)
        for et in result["emitted"]:
            source = et.test_path.read_text()
            assert source.strip(), "emitted test file must not be empty"
            ast.parse(source)  # must be valid Python

    def test_bijection_is_bijective_for_normal_input(self, tmp_path):
        acs = ["File exists: src/a.py", "Function defined: bob.a.fn"]
        result = generate_failing_tests("feat-tw-bij", acs, workspace=tmp_path)
        assert result["bijection"].is_bijective is True

    def test_invalid_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            generate_failing_tests("", ["File exists: src/x.py"], workspace=tmp_path)

    def test_non_list_ac_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            generate_failing_tests("feat-tw-err", "not-a-list", workspace=tmp_path)  # type: ignore[arg-type]


class TestFilterByCompilation:
    def _make_emitted(self, tmp_path: Path, ac_text: str, source: str, idx: int = 0) -> EmittedTest:
        feat_dir = tmp_path / "tests" / "feat-comp"
        feat_dir.mkdir(parents=True, exist_ok=True)
        path = feat_dir / f"test_ac_{idx}.py"
        path.write_text(source, encoding="utf-8")
        return EmittedTest(
            ac_index=idx,
            ac_id=f"ac_{idx}",
            ac_text=ac_text,
            test_path=path,
            feature_id="feat-comp",
        )

    def test_valid_test_is_kept(self, tmp_path):
        source = "import pytest\ndef test_x():\n    pytest.fail('not implemented')\n"
        et = self._make_emitted(tmp_path, "File exists: src/x.py", source)
        result = filter_by_compilation([et])
        assert result == [et]

    def test_syntax_error_is_rejected(self, tmp_path):
        source = "def test_x(\n"  # invalid syntax
        et = self._make_emitted(tmp_path, "File exists: src/x.py", source)
        result = filter_by_compilation([et])
        assert result == []

    def test_empty_list_returns_empty_list(self, tmp_path):
        assert filter_by_compilation([]) == []

    def test_non_list_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="emitted_tests"):
            filter_by_compilation("not-a-list")  # type: ignore[arg-type]


class TestFilterByStubPass:
    def _make_emitted(self, tmp_path: Path, source: str, idx: int = 0) -> EmittedTest:
        feat_dir = tmp_path / "tests" / "feat-stub"
        feat_dir.mkdir(parents=True, exist_ok=True)
        path = feat_dir / f"test_ac_{idx}.py"
        path.write_text(source, encoding="utf-8")
        return EmittedTest(
            ac_index=idx,
            ac_id=f"ac_{idx}",
            ac_text="some AC",
            test_path=path,
            feature_id="feat-stub",
        )

    def test_failing_test_is_kept(self, tmp_path):
        source = "import pytest\ndef test_x():\n    pytest.fail('not implemented')\n"
        et = self._make_emitted(tmp_path, source)
        result = filter_by_stub_pass([et])
        assert result == [et]

    def test_empty_list_returns_empty_list(self, tmp_path):
        assert filter_by_stub_pass([]) == []

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="emitted_tests"):
            filter_by_stub_pass(None)  # type: ignore[arg-type]


class TestFilterByCoverage:
    def _make_emitted(self, tmp_path: Path, source: str, idx: int = 0) -> EmittedTest:
        feat_dir = tmp_path / "tests" / "feat-cov"
        feat_dir.mkdir(parents=True, exist_ok=True)
        path = feat_dir / f"test_ac_{idx}.py"
        path.write_text(source, encoding="utf-8")
        return EmittedTest(
            ac_index=idx,
            ac_id=f"ac_{idx}",
            ac_text="some AC",
            test_path=path,
            feature_id="feat-cov",
        )

    def test_test_with_non_pytest_import_is_kept(self, tmp_path):
        source = "import pathlib\nimport pytest\ndef test_x():\n    assert pathlib.Path('.').exists()\n"
        et = self._make_emitted(tmp_path, source)
        result = filter_by_coverage([et])
        assert result == [et]

    def test_pytest_fail_call_passes_coverage_heuristic(self, tmp_path):
        # pytest.fail() is counted as a non-trivial call in the coverage heuristic
        source = "import pytest\ndef test_x():\n    pytest.fail('nope')\n"
        et = self._make_emitted(tmp_path, source)
        result = filter_by_coverage([et])
        assert result == [et]

    def test_empty_list_returns_empty_list(self, tmp_path):
        assert filter_by_coverage([]) == []

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="emitted_tests"):
            filter_by_coverage(42)  # type: ignore[arg-type]


class TestBuildPassCoverageFilter:
    """The TestGen-LLM Build/Pass/Coverage triple filter combined into one pass."""

    def _make_emitted(self, tmp_path: Path, source: str, idx: int = 0) -> EmittedTest:
        feat_dir = tmp_path / "tests" / "feat-bpc"
        feat_dir.mkdir(parents=True, exist_ok=True)
        path = feat_dir / f"test_ac_{idx}.py"
        path.write_text(source, encoding="utf-8")
        return EmittedTest(
            ac_index=idx,
            ac_id=f"ac_{idx}",
            ac_text="some AC",
            test_path=path,
            feature_id="feat-bpc",
        )

    def test_keeps_test_passing_all_three_checks(self, tmp_path):
        # compiles, fails on stub (pytest.fail), references non-pytest symbol
        source = "import pathlib\nimport pytest\ndef test_x():\n    pytest.fail('nope')\n"
        et = self._make_emitted(tmp_path, source)
        assert build_pass_coverage_filter([et]) == [et]

    def test_rejects_uncompilable_test(self, tmp_path):
        source = "def broken(:\n    pass\n"
        et = self._make_emitted(tmp_path, source)
        assert build_pass_coverage_filter([et]) == []

    def test_rejects_test_passing_on_stub(self, tmp_path):
        source = "def test_x():\n    assert True\n"
        et = self._make_emitted(tmp_path, source)
        assert build_pass_coverage_filter([et]) == []

    def test_empty_list_returns_empty_list(self, tmp_path):
        assert build_pass_coverage_filter([]) == []

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="emitted_tests"):
            build_pass_coverage_filter(42)  # type: ignore[arg-type]

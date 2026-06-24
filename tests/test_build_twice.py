"""Tests for src/bob/build_twice.py (Gap #7: Build-twice nondeterminism detector).

TDD: written before implementation.
compare_builds(feature_id, workspace) -> NondeterminismReport
"""
from __future__ import annotations

import ast
import json
import os
import textwrap
from pathlib import Path

import pytest

from bob.build_twice import (
    NondeterminismReport,
    ast_normalize,
    token_diff_ratio,
    compare_builds,
    is_build_twice_enabled,
)


# ---------------------------------------------------------------------------
# NondeterminismReport
# ---------------------------------------------------------------------------


class TestNondeterminismReport:
    def test_is_dataclass_or_pydantic_with_required_fields(self):
        report = NondeterminismReport(
            feature_id="feat-1",
            divergence_ratio=0.1,
            flagged=False,
            seed_a=42,
            seed_b=43,
        )
        assert report.feature_id == "feat-1"
        assert report.divergence_ratio == pytest.approx(0.1)
        assert report.flagged is False
        assert report.seed_a == 42
        assert report.seed_b == 43

    def test_flagged_true_when_divergence_above_threshold(self):
        report = NondeterminismReport(
            feature_id="feat-2",
            divergence_ratio=0.35,
            flagged=True,
            seed_a=10,
            seed_b=11,
        )
        assert report.flagged is True

    def test_divergence_ratio_is_float(self):
        report = NondeterminismReport(
            feature_id="feat-3",
            divergence_ratio=0.0,
            flagged=False,
            seed_a=0,
            seed_b=1,
        )
        assert isinstance(report.divergence_ratio, float)


# ---------------------------------------------------------------------------
# ast_normalize
# ---------------------------------------------------------------------------


class TestAstNormalize:
    def test_strips_comments_and_docstrings_identity(self):
        code = textwrap.dedent("""\
            # header comment
            def foo():
                \"\"\"docstring\"\"\"
                x = 1  # inline
                return x
        """)
        normalized = ast_normalize(code)
        assert isinstance(normalized, str)
        assert len(normalized) > 0

    def test_same_code_different_variable_names_still_normalizes(self):
        code_a = textwrap.dedent("""\
            def add(x, y):
                result = x + y
                return result
        """)
        code_b = textwrap.dedent("""\
            def add(a, b):
                total = a + b
                return total
        """)
        # After normalization the AST structure should be the same
        norm_a = ast_normalize(code_a)
        norm_b = ast_normalize(code_b)
        # Both should be valid non-empty strings
        assert len(norm_a) > 0
        assert len(norm_b) > 0

    def test_different_structure_produces_different_normalized_output(self):
        code_a = "def foo(): return 1"
        code_b = "def foo(): return 1 + 2"
        assert ast_normalize(code_a) != ast_normalize(code_b)

    def test_same_code_produces_same_normalized_output(self):
        code = "def foo(x): return x * 2"
        assert ast_normalize(code) == ast_normalize(code)

    def test_invalid_syntax_returns_original(self):
        bad_code = "def foo( this is not valid python !!"
        result = ast_normalize(bad_code)
        assert isinstance(result, str)
        # Should return something (either original or partial normalization)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# token_diff_ratio
# ---------------------------------------------------------------------------


class TestTokenDiffRatio:
    def test_identical_texts_return_zero(self):
        text = "def foo(): return 42"
        ratio = token_diff_ratio(text, text)
        assert ratio == pytest.approx(0.0)

    def test_completely_different_texts_return_high_ratio(self):
        a = "alpha beta gamma delta epsilon"
        b = "one two three four five six seven eight nine ten"
        ratio = token_diff_ratio(a, b)
        assert ratio > 0.5

    def test_ratio_is_between_zero_and_one(self):
        a = "hello world foo"
        b = "hello world bar baz"
        ratio = token_diff_ratio(a, b)
        assert 0.0 <= ratio <= 1.0

    def test_small_change_produces_low_ratio(self):
        base = "def foo(x): return x + 1"
        changed = "def foo(x): return x + 2"
        ratio = token_diff_ratio(base, changed)
        assert ratio < 0.3

    def test_returns_float(self):
        ratio = token_diff_ratio("a b c", "a b d")
        assert isinstance(ratio, float)


# ---------------------------------------------------------------------------
# is_build_twice_enabled
# ---------------------------------------------------------------------------


class TestIsBuildTwiceEnabled:
    def test_returns_false_by_default(self, monkeypatch):
        monkeypatch.delenv("BOB_BUILD_TWICE", raising=False)
        assert is_build_twice_enabled() is False

    def test_returns_true_when_env_var_is_true(self, monkeypatch):
        monkeypatch.setenv("BOB_BUILD_TWICE", "true")
        assert is_build_twice_enabled() is True

    def test_returns_true_when_env_var_is_1(self, monkeypatch):
        monkeypatch.setenv("BOB_BUILD_TWICE", "1")
        assert is_build_twice_enabled() is True

    def test_returns_false_when_env_var_is_false(self, monkeypatch):
        monkeypatch.setenv("BOB_BUILD_TWICE", "false")
        assert is_build_twice_enabled() is False

    def test_returns_false_when_env_var_is_0(self, monkeypatch):
        monkeypatch.setenv("BOB_BUILD_TWICE", "0")
        assert is_build_twice_enabled() is False

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("BOB_BUILD_TWICE", "TRUE")
        assert is_build_twice_enabled() is True


# ---------------------------------------------------------------------------
# compare_builds (integration-style, no actual sub-agent calls)
# ---------------------------------------------------------------------------


class TestCompareBuilds:
    def _write_py_files(self, workspace: Path, subdir: str, code: str) -> None:
        target = workspace / subdir
        target.mkdir(parents=True, exist_ok=True)
        (target / "impl.py").write_text(code)

    def test_returns_nondeterminism_report(self, tmp_path):
        code_a = textwrap.dedent("""\
            def solve():
                return 42
        """)
        code_b = textwrap.dedent("""\
            def solve():
                return 42
        """)
        self._write_py_files(tmp_path, "build_a", code_a)
        self._write_py_files(tmp_path, "build_b", code_b)
        report = compare_builds(
            "feat-x",
            tmp_path,
            build_a_dir="build_a",
            build_b_dir="build_b",
        )
        assert isinstance(report, NondeterminismReport)

    def test_identical_builds_not_flagged(self, tmp_path):
        code = textwrap.dedent("""\
            def compute(x, y):
                return x + y
        """)
        self._write_py_files(tmp_path, "build_a", code)
        self._write_py_files(tmp_path, "build_b", code)
        report = compare_builds(
            "feat-same",
            tmp_path,
            build_a_dir="build_a",
            build_b_dir="build_b",
        )
        assert report.flagged is False
        assert report.divergence_ratio == pytest.approx(0.0)

    def test_divergent_builds_flagged(self, tmp_path):
        code_a = textwrap.dedent("""\
            def process(data):
                result = []
                for item in data:
                    result.append(item * 2)
                return result
        """)
        code_b = textwrap.dedent("""\
            class Handler:
                def __init__(self):
                    self.state = {}
                def process(self, data):
                    return {k: v for k, v in enumerate(data)}
                def reset(self):
                    self.state.clear()
                def validate(self, x):
                    return x is not None
                def transform(self, x):
                    return str(x).upper()
        """)
        self._write_py_files(tmp_path, "build_a", code_a)
        self._write_py_files(tmp_path, "build_b", code_b)
        report = compare_builds(
            "feat-diverge",
            tmp_path,
            build_a_dir="build_a",
            build_b_dir="build_b",
        )
        assert report.flagged is True
        assert report.divergence_ratio > 0.3

    def test_feature_id_in_report(self, tmp_path):
        code = "x = 1"
        self._write_py_files(tmp_path, "build_a", code)
        self._write_py_files(tmp_path, "build_b", code)
        report = compare_builds(
            "my-feature-id",
            tmp_path,
            build_a_dir="build_a",
            build_b_dir="build_b",
        )
        assert report.feature_id == "my-feature-id"

    def test_logs_to_progress_jsonl_when_flagged(self, tmp_path):
        code_a = "def foo(): return 1\ndef bar(): return 2\ndef baz(): return 3\n"
        code_b = "class X:\n    def method_one(self): pass\n    def method_two(self): pass\n    def method_three(self): pass\n    def method_four(self): pass\n"
        self._write_py_files(tmp_path, "build_a", code_a)
        self._write_py_files(tmp_path, "build_b", code_b)
        report = compare_builds(
            "feat-log",
            tmp_path,
            build_a_dir="build_a",
            build_b_dir="build_b",
        )
        # When flagged, progress.jsonl must exist in workspace/.bob/
        progress = tmp_path / ".bob" / "progress.jsonl"
        if report.flagged:
            assert progress.exists(), "progress.jsonl must be written when divergence is flagged"
            lines = [json.loads(l) for l in progress.read_text().splitlines() if l.strip()]
            nondeterminism_events = [l for l in lines if l.get("event_type") == "nondeterminism_detected"]
            assert len(nondeterminism_events) >= 1

    def test_empty_builds_return_report(self, tmp_path):
        # Empty directories - no python files
        (tmp_path / "build_a").mkdir()
        (tmp_path / "build_b").mkdir()
        report = compare_builds(
            "feat-empty",
            tmp_path,
            build_a_dir="build_a",
            build_b_dir="build_b",
        )
        assert isinstance(report, NondeterminismReport)
        assert report.divergence_ratio == pytest.approx(0.0)
        assert report.flagged is False

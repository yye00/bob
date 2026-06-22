"""Tests for test_implementation_coupling_detector (feature 884b9e46).

Verifies that ``bob3.test_implementation_coupling_detector`` exports the full
public API and that the top-level ``check_test_impl_coupling`` function works
correctly end-to-end.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob3.test_implementation_coupling_detector import (
    CouplingFinding,
    CouplingResult,
    check_test_impl_coupling,
    detect_identical_constants,
    detect_internal_imports,
    detect_shared_helpers,
)


def _write(tmp_path: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


class TestModuleExports:
    """Verify the canonical module exports all expected symbols."""

    def test_coupling_finding_constructible(self):
        f = CouplingFinding(
            kind="internal_import",
            test_file="tests/test_foo.py",
            impl_file="src/bob3/foo.py",
            detail="relative import detected",
        )
        assert f.kind == "internal_import"
        assert f.test_file == "tests/test_foo.py"
        assert f.impl_file == "src/bob3/foo.py"

    def test_coupling_result_constructible(self):
        r = CouplingResult(is_flagged=False, findings=[], summary="clean")
        assert r.is_flagged is False
        assert r.findings == []
        assert r.summary == "clean"

    def test_detect_internal_imports_callable(self, tmp_path):
        findings = detect_internal_imports(workspace=tmp_path)
        assert isinstance(findings, list)

    def test_detect_shared_helpers_callable(self, tmp_path):
        findings = detect_shared_helpers(workspace=tmp_path)
        assert isinstance(findings, list)

    def test_detect_identical_constants_callable(self, tmp_path):
        findings = detect_identical_constants(workspace=tmp_path)
        assert isinstance(findings, list)

    def test_check_test_impl_coupling_callable(self, tmp_path):
        result = check_test_impl_coupling(workspace=tmp_path)
        assert isinstance(result, CouplingResult)


class TestDetectInternalImports:
    def test_relative_import_flagged(self, tmp_path):
        _write(tmp_path, "tests/test_rel.py", """\
            from ..src.pkg import impl
            def test_it(): pass
        """)
        findings = detect_internal_imports(workspace=tmp_path)
        assert len(findings) >= 1
        assert all(f.kind == "internal_import" for f in findings)

    def test_private_module_import_flagged(self, tmp_path):
        _write(tmp_path, "tests/test_priv.py", """\
            from bob3._private import helper
            def test_it(): pass
        """)
        findings = detect_internal_imports(workspace=tmp_path)
        assert len(findings) >= 1
        assert any("_private" in f.detail for f in findings)

    def test_public_import_not_flagged(self, tmp_path):
        _write(tmp_path, "tests/test_pub.py", """\
            from bob3.public_api import fn
            def test_fn(): assert fn() is not None
        """)
        findings = detect_internal_imports(workspace=tmp_path)
        assert findings == []

    def test_empty_workspace_returns_empty(self, tmp_path):
        assert detect_internal_imports(workspace=tmp_path) == []


class TestDetectSharedHelpers:
    def test_identical_helper_flagged(self, tmp_path):
        code = """\
            def _normalize(text):
                return text.strip().lower()
        """
        _write(tmp_path, "src/pkg/utils.py", code)
        _write(tmp_path, "tests/test_utils.py", code)
        findings = detect_shared_helpers(workspace=tmp_path)
        assert len(findings) >= 1
        assert any(f.kind == "shared_helper" for f in findings)

    def test_different_helpers_not_flagged(self, tmp_path):
        _write(tmp_path, "src/pkg/impl.py", """\
            def compute(x):
                return x * x * x
        """)
        _write(tmp_path, "tests/test_impl.py", """\
            def build_fixture(n):
                return list(range(n))
        """)
        assert detect_shared_helpers(workspace=tmp_path) == []

    def test_trivial_functions_excluded(self, tmp_path):
        _write(tmp_path, "src/pkg/a.py", "def noop(): pass")
        _write(tmp_path, "tests/test_a.py", "def noop(): pass")
        assert detect_shared_helpers(workspace=tmp_path) == []


class TestDetectIdenticalConstants:
    def test_same_name_and_value_flagged(self, tmp_path):
        _write(tmp_path, "src/pkg/cfg.py", "MAX_RETRIES = 5")
        _write(tmp_path, "tests/test_cfg.py", "MAX_RETRIES = 5")
        findings = detect_identical_constants(workspace=tmp_path)
        assert len(findings) >= 1
        assert any(f.kind == "identical_constant" for f in findings)
        assert any("MAX_RETRIES" in f.detail for f in findings)

    def test_same_name_different_value_not_flagged(self, tmp_path):
        _write(tmp_path, "src/pkg/cfg.py", "TIMEOUT = 30")
        _write(tmp_path, "tests/test_cfg.py", "TIMEOUT = 1")
        assert detect_identical_constants(workspace=tmp_path) == []

    def test_no_src_returns_empty(self, tmp_path):
        _write(tmp_path, "tests/test_only.py", "MAGIC = 99")
        assert detect_identical_constants(workspace=tmp_path) == []


class TestCheckTestImplCoupling:
    def test_clean_workspace_not_flagged(self, tmp_path):
        _write(tmp_path, "src/pkg/__init__.py", "")
        _write(tmp_path, "src/pkg/impl.py", """\
            def compute(x):
                return x * 2
        """)
        _write(tmp_path, "tests/test_impl.py", """\
            from pkg.impl import compute
            def test_compute():
                assert compute(3) == 6
        """)
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is False
        assert result.findings == []

    def test_internal_import_causes_flag(self, tmp_path):
        _write(tmp_path, "tests/test_priv.py", """\
            from pkg._internals import _helper
            def test_helper(): assert _helper(0) == 0
        """)
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is True
        assert len(result.findings) >= 1

    def test_shared_constant_causes_flag(self, tmp_path):
        _write(tmp_path, "src/pkg/cfg.py", "API_KEY_LEN = 32")
        _write(tmp_path, "tests/test_cfg.py", "API_KEY_LEN = 32")
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is True

    def test_shared_helper_causes_flag(self, tmp_path):
        code = """\
            def _normalize(text):
                return text.strip().lower()
        """
        _write(tmp_path, "src/pkg/utils.py", code)
        _write(tmp_path, "tests/test_utils.py", code)
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is True

    def test_summary_is_string(self, tmp_path):
        result = check_test_impl_coupling(workspace=tmp_path)
        assert isinstance(result.summary, str)

    def test_nonexistent_workspace_returns_clean(self, tmp_path):
        result = check_test_impl_coupling(workspace=tmp_path / "missing")
        assert result.is_flagged is False

    def test_flagged_result_has_nonempty_summary(self, tmp_path):
        _write(tmp_path, "src/pkg/cfg.py", "LIMIT = 100")
        _write(tmp_path, "tests/test_cfg.py", "LIMIT = 100")
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is True
        assert len(result.summary) > 0

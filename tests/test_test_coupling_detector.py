"""Tests for the test-implementation coupling detector (feature 884b9e46).

The detector flags suspicious structural coupling between test files and
implementation files:
  1. Direct internal imports — a test file imports from a src/ module using
     relative imports or absolute internal package imports that would only work
     from inside the package (not the public API).
  2. Shared helper functions — the same helper function name (with identical
     normalized AST structure) appears in both a test file and an impl file.
  3. Identical constant definitions — the same constant name bound to the same
     value appears verbatim in both test and impl files.

Hard-fail semantics: if any coupling is detected, the check returns False.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.test_coupling_detector import (
    CouplingFinding,
    CouplingResult,
    check_test_impl_coupling,
    detect_internal_imports,
    detect_shared_helpers,
    detect_identical_constants,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# CouplingFinding / CouplingResult data model tests
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_coupling_finding_has_required_fields(self):
        f = CouplingFinding(
            kind="internal_import",
            test_file="tests/test_foo.py",
            impl_file="src/bob/foo.py",
            detail="tests/test_foo.py imports src/bob/foo directly",
        )
        assert f.kind == "internal_import"
        assert f.test_file == "tests/test_foo.py"
        assert f.impl_file == "src/bob/foo.py"
        assert "foo" in f.detail

    def test_coupling_result_clean(self):
        r = CouplingResult(is_flagged=False, findings=[], summary="No coupling detected")
        assert r.is_flagged is False
        assert r.findings == []

    def test_coupling_result_flagged(self):
        f = CouplingFinding(
            kind="identical_constant",
            test_file="tests/test_bar.py",
            impl_file="src/bob/bar.py",
            detail="TIMEOUT = 30 in both files",
        )
        r = CouplingResult(is_flagged=True, findings=[f], summary="1 coupling(s) found")
        assert r.is_flagged is True
        assert len(r.findings) == 1


# ---------------------------------------------------------------------------
# detect_internal_imports — test files importing internal src modules
# ---------------------------------------------------------------------------


class TestDetectInternalImports:
    """Tests that detect_internal_imports flags suspicious internal imports."""

    def test_no_imports_passes(self, tmp_path):
        _write(tmp_path, "tests/test_clean.py", """\
            import pytest

            def test_something():
                assert 1 + 1 == 2
        """)
        findings = detect_internal_imports(workspace=tmp_path)
        assert findings == []

    def test_public_api_import_not_flagged(self, tmp_path):
        """Importing the top-level package is fine (public API)."""
        _write(tmp_path, "src/mypackage/__init__.py", "")
        _write(tmp_path, "src/mypackage/public.py", "ANSWER = 42")
        _write(tmp_path, "tests/test_pub.py", """\
            from mypackage import public

            def test_public():
                assert public.ANSWER == 42
        """)
        findings = detect_internal_imports(workspace=tmp_path)
        assert findings == []

    def test_relative_import_from_test_file_flagged(self, tmp_path):
        """Relative imports in test files are always suspicious."""
        _write(tmp_path, "tests/test_rel.py", """\
            from ..src.mypackage import impl

            def test_it():
                assert impl.run() is not None
        """)
        findings = detect_internal_imports(workspace=tmp_path)
        assert len(findings) >= 1
        kinds = [f.kind for f in findings]
        assert "internal_import" in kinds

    def test_direct_src_submodule_import_flagged(self, tmp_path):
        """Importing bob.internal or bob._private from a test file is flagged."""
        _write(tmp_path, "src/bob/__init__.py", "")
        _write(tmp_path, "src/bob/_internal.py", "SECRET = 'x'")
        _write(tmp_path, "tests/test_internal.py", """\
            from bob._internal import SECRET

            def test_secret():
                assert SECRET == 'x'
        """)
        findings = detect_internal_imports(workspace=tmp_path)
        assert len(findings) >= 1
        assert any("_internal" in f.detail for f in findings)

    def test_underscore_private_module_import_flagged(self, tmp_path):
        """Any import of a module starting with _ is flagged as internal."""
        _write(tmp_path, "tests/test_priv.py", """\
            from bob._helpers import _helper_fn

            def test_helper():
                assert _helper_fn(0) == 0
        """)
        findings = detect_internal_imports(workspace=tmp_path)
        assert len(findings) >= 1

    def test_no_test_files_returns_empty(self, tmp_path):
        _write(tmp_path, "src/mypackage/impl.py", "def run(): return 1")
        findings = detect_internal_imports(workspace=tmp_path)
        assert findings == []

    def test_syntax_error_in_test_skipped_gracefully(self, tmp_path):
        _write(tmp_path, "tests/test_broken.py", "def (broken syntax:")
        findings = detect_internal_imports(workspace=tmp_path)
        assert isinstance(findings, list)  # no crash


# ---------------------------------------------------------------------------
# detect_shared_helpers — same helper function appears in test and impl
# ---------------------------------------------------------------------------


class TestDetectSharedHelpers:
    """Tests that detect_shared_helpers flags functions shared between test and impl."""

    def test_no_shared_helpers_passes(self, tmp_path):
        _write(tmp_path, "src/mypackage/impl.py", """\
            def compute(x):
                return x * 2
        """)
        _write(tmp_path, "tests/test_impl.py", """\
            def helper_for_test(x):
                return x + 1
        """)
        findings = detect_shared_helpers(workspace=tmp_path)
        assert findings == []

    def test_identical_helper_in_test_and_impl_flagged(self, tmp_path):
        helper_code = """\
            def _normalize(text):
                return text.strip().lower()
        """
        _write(tmp_path, "src/mypackage/utils.py", helper_code)
        _write(tmp_path, "tests/test_utils.py", helper_code)
        findings = detect_shared_helpers(workspace=tmp_path)
        assert len(findings) >= 1
        assert any(f.kind == "shared_helper" for f in findings)
        assert any("_normalize" in f.detail for f in findings)

    def test_renamed_but_identical_structure_flagged(self, tmp_path):
        """Same AST structure even with different name is still flagged."""
        _write(tmp_path, "src/pkg/algo.py", """\
            def _normalize(text):
                return text.strip().lower()
        """)
        _write(tmp_path, "tests/test_algo.py", """\
            def _clean(text):
                return text.strip().lower()
        """)
        findings = detect_shared_helpers(workspace=tmp_path)
        assert len(findings) >= 1

    def test_different_functions_not_flagged(self, tmp_path):
        _write(tmp_path, "src/pkg/code.py", """\
            def compute_sum(items):
                total = 0
                for item in items:
                    total += item
                return total
        """)
        _write(tmp_path, "tests/test_code.py", """\
            def make_list(n):
                return list(range(n))
        """)
        findings = detect_shared_helpers(workspace=tmp_path)
        assert findings == []

    def test_small_trivial_functions_not_flagged(self, tmp_path):
        """Single-line trivial functions (len <= 1 stmt) should not be flagged."""
        _write(tmp_path, "src/pkg/a.py", """\
            def noop():
                pass
        """)
        _write(tmp_path, "tests/test_a.py", """\
            def noop():
                pass
        """)
        findings = detect_shared_helpers(workspace=tmp_path)
        # Trivial (1-statement) functions are below the minimum threshold
        assert findings == []


# ---------------------------------------------------------------------------
# detect_identical_constants — same constant defined in both test and impl
# ---------------------------------------------------------------------------


class TestDetectIdenticalConstants:
    """Tests that detect_identical_constants flags constants defined in both."""

    def test_no_shared_constants_passes(self, tmp_path):
        _write(tmp_path, "src/pkg/config.py", "TIMEOUT = 30")
        _write(tmp_path, "tests/test_cfg.py", "MY_TIMEOUT = 99")
        findings = detect_identical_constants(workspace=tmp_path)
        assert findings == []

    def test_same_constant_name_and_value_flagged(self, tmp_path):
        _write(tmp_path, "src/pkg/constants.py", "MAX_RETRIES = 5")
        _write(tmp_path, "tests/test_constants.py", "MAX_RETRIES = 5")
        findings = detect_identical_constants(workspace=tmp_path)
        assert len(findings) >= 1
        assert any(f.kind == "identical_constant" for f in findings)
        assert any("MAX_RETRIES" in f.detail for f in findings)

    def test_same_name_different_value_not_flagged(self, tmp_path):
        """Same name but different value is just test scaffolding, not coupling."""
        _write(tmp_path, "src/pkg/cfg.py", "TIMEOUT = 30")
        _write(tmp_path, "tests/test_cfg.py", "TIMEOUT = 1")  # test uses short timeout
        findings = detect_identical_constants(workspace=tmp_path)
        assert findings == []

    def test_string_constant_flagged(self, tmp_path):
        _write(tmp_path, "src/pkg/defaults.py", 'DEFAULT_URL = "http://localhost:8080"')
        _write(tmp_path, "tests/test_defaults.py", 'DEFAULT_URL = "http://localhost:8080"')
        findings = detect_identical_constants(workspace=tmp_path)
        assert len(findings) >= 1
        assert any("DEFAULT_URL" in f.detail for f in findings)

    def test_common_pytest_constants_excluded(self, tmp_path):
        """Well-known test constants like pytestmark should not be flagged."""
        _write(tmp_path, "src/pkg/mod.py", "")
        _write(tmp_path, "tests/test_mod.py", "pytestmark = pytest.mark.unit")
        findings = detect_identical_constants(workspace=tmp_path)
        assert findings == []

    def test_no_src_files_returns_empty(self, tmp_path):
        _write(tmp_path, "tests/test_only.py", "CONST = 42")
        findings = detect_identical_constants(workspace=tmp_path)
        assert findings == []


# ---------------------------------------------------------------------------
# check_test_impl_coupling — top-level integration
# ---------------------------------------------------------------------------


class TestCheckTestImplCoupling:
    """Integration tests for the top-level check_test_impl_coupling function."""

    def test_clean_workspace_passes(self, tmp_path):
        _write(tmp_path, "src/pkg/__init__.py", "")
        _write(tmp_path, "src/pkg/impl.py", """\
            def compute(x):
                return x * 2
        """)
        _write(tmp_path, "tests/test_impl.py", """\
            import pytest
            from pkg.impl import compute

            def test_compute():
                assert compute(3) == 6
        """)
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is False
        assert result.findings == []

    def test_workspace_with_internal_import_fails(self, tmp_path):
        _write(tmp_path, "tests/test_priv.py", """\
            from pkg._internals import _helper

            def test_helper():
                assert _helper(0) == 0
        """)
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is True
        assert len(result.findings) >= 1

    def test_workspace_with_shared_constant_fails(self, tmp_path):
        _write(tmp_path, "src/pkg/cfg.py", "API_KEY_LEN = 32")
        _write(tmp_path, "tests/test_cfg.py", "API_KEY_LEN = 32")
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is True

    def test_workspace_with_shared_helper_fails(self, tmp_path):
        helper = """\
            def _normalize(text):
                return text.strip().lower()
        """
        _write(tmp_path, "src/pkg/utils.py", helper)
        _write(tmp_path, "tests/test_utils.py", helper)
        result = check_test_impl_coupling(workspace=tmp_path)
        assert result.is_flagged is True

    def test_result_summary_present(self, tmp_path):
        _write(tmp_path, "src/pkg/cfg.py", "MAGIC = 42")
        _write(tmp_path, "tests/test_cfg.py", "MAGIC = 42")
        result = check_test_impl_coupling(workspace=tmp_path)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_nonexistent_workspace_returns_clean(self, tmp_path):
        """Missing workspace should not crash; return clean result."""
        missing = tmp_path / "does_not_exist"
        result = check_test_impl_coupling(workspace=missing)
        assert result.is_flagged is False


# ---------------------------------------------------------------------------
# Criterion form: test_coupling: via enhanced_verification
# ---------------------------------------------------------------------------


class TestCriterionForm:
    """Tests that the test_coupling: criterion integrates with _check_criterion_with_details."""

    def test_clean_workspace_criterion_passes(self, tmp_path):
        from bob.enhanced_verification import _check_criterion_with_details

        _write(tmp_path, "src/pkg/__init__.py", "")
        _write(tmp_path, "tests/test_clean.py", """\
            def test_trivial():
                assert True
        """)
        passed, details = _check_criterion_with_details(
            criterion="test_coupling:",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_coupled_workspace_criterion_fails(self, tmp_path):
        from bob.enhanced_verification import _check_criterion_with_details

        _write(tmp_path, "src/pkg/cfg.py", "MAGIC = 42")
        _write(tmp_path, "tests/test_cfg.py", "MAGIC = 42")
        passed, details = _check_criterion_with_details(
            criterion="test_coupling:",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert details  # should explain what was found

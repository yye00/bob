"""Tests for F122: AST-Based Stub and Mock Detection.

Validates that ast-based analysis correctly identifies:
- Stub functions (pass-only, ellipsis-only, raise-NotImplementedError-only bodies)
- Mock imports/usage in src/ files (flagged) vs tests/ files (allowed)

CRITICAL: Must avoid false positives:
- 'except Exception: pass' is valid code, NOT a stub
- Only flag functions where the ENTIRE body is a stub pattern
"""

import textwrap

import pytest

from bob3.ast_checks import (
    StubFinding,
    MockFinding,
    detect_mock_usage,
    detect_stub_functions,
    verify_no_stubs_or_mocks,
)


# ============================================================
# STEP 1 & 2: _detect_stub_functions with ast.walk()
# ============================================================


class TestDetectStubFunctions:
    """Test stub function detection using AST analysis."""

    def test_pass_only_function_flagged(self):
        """Step 5: 'def foo(): pass' should be flagged as stub."""
        source = textwrap.dedent("""\
            def foo():
                pass
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "foo"
        assert findings[0].filepath == "src/example.py"
        assert "pass" in findings[0].reason.lower()

    def test_ellipsis_only_function_flagged(self):
        """Functions with only '...' as body should be flagged."""
        source = textwrap.dedent("""\
            def bar():
                ...
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "bar"
        assert "ellipsis" in findings[0].reason.lower()

    def test_raise_not_implemented_function_flagged(self):
        """Functions that only raise NotImplementedError should be flagged."""
        source = textwrap.dedent("""\
            def baz():
                raise NotImplementedError
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "baz"
        assert "notimplementederror" in findings[0].reason.lower()

    def test_raise_not_implemented_with_message_flagged(self):
        """Functions that raise NotImplementedError('msg') should be flagged."""
        source = textwrap.dedent("""\
            def baz():
                raise NotImplementedError("todo")
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "baz"

    def test_docstring_then_pass_flagged(self):
        """Step 3: Functions with docstring + pass should be flagged (skip docstring)."""
        source = textwrap.dedent("""\
            def documented_stub():
                \"\"\"This function does something.\"\"\"
                pass
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "documented_stub"

    def test_docstring_then_ellipsis_flagged(self):
        """Functions with docstring + ... should be flagged."""
        source = textwrap.dedent("""\
            def another_stub():
                \"\"\"Docstring.\"\"\"
                ...
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "another_stub"

    def test_docstring_then_raise_not_implemented_flagged(self):
        """Functions with docstring + raise NotImplementedError should be flagged."""
        source = textwrap.dedent("""\
            def yet_another():
                \"\"\"Docstring.\"\"\"
                raise NotImplementedError
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "yet_another"

    def test_async_function_stub_flagged(self):
        """Step 2: AsyncFunctionDef nodes should also be checked."""
        source = textwrap.dedent("""\
            async def async_stub():
                pass
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "async_stub"

    def test_real_function_not_flagged(self):
        """Real functions with actual logic should NOT be flagged."""
        source = textwrap.dedent("""\
            def real_function(x):
                result = x * 2
                return result
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 0

    def test_except_pass_not_flagged(self):
        """Step 6: 'except Error: pass' should NOT be flagged (valid code)."""
        source = textwrap.dedent("""\
            def robust_function():
                try:
                    do_something()
                except Exception:
                    pass
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 0

    def test_except_pass_with_other_logic_not_flagged(self):
        """Functions with try/except pass AND other logic are valid."""
        source = textwrap.dedent("""\
            def another_robust():
                x = 1
                try:
                    risky_call()
                except ValueError:
                    pass
                return x
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 0

    def test_multiple_stubs_all_flagged(self):
        """Multiple definitive stub functions should all be detected at error severity.

        ``real_one`` here returns a literal (42), which is a *warning*-level
        heuristic, not an error. We assert specifically about error-severity
        findings to keep the original contract: the three definitive stubs
        are all flagged at error.
        """
        source = textwrap.dedent("""\
            def stub1():
                pass

            def stub2():
                ...

            def real_one():
                return 42

            def stub3():
                raise NotImplementedError
        """)
        findings = detect_stub_functions(source, "src/example.py")
        error_findings = [f for f in findings if f.severity == "error"]
        assert len(error_findings) == 3
        names = {f.function_name for f in error_findings}
        assert names == {"stub1", "stub2", "stub3"}

    def test_class_method_stub_flagged(self):
        """Stub methods inside classes should be flagged."""
        source = textwrap.dedent("""\
            class MyClass:
                def method_stub(self):
                    pass
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "method_stub"

    def test_function_with_only_return_none_flagged_as_warning(self):
        """A function whose entire body is ``return None`` is a heuristic stub.

        This used to be allowed (the original ast_checks only caught
        pass/.../raise NotImplementedError) which let a determined agent
        bypass the detector with ``return None``. The literal-return heuristic
        catches that at ``severity="warning"`` — softer than error so legacy
        callers gating on ``passed`` are unaffected, but the finding is still
        surfaced for review.
        """
        source = textwrap.dedent("""\
            def returns_none():
                return None
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "returns_none"
        assert findings[0].severity == "warning"
        # Definitive (error) stubs must NOT increase from this case.
        error_findings = [f for f in findings if f.severity == "error"]
        assert error_findings == []

    def test_invalid_syntax_returns_empty(self):
        """Invalid Python source should not crash, returns empty list."""
        source = "def broken(:\n    pass"
        findings = detect_stub_functions(source, "src/broken.py")
        assert findings == []

    def test_finding_has_line_number(self):
        """StubFinding should include the line number."""
        source = textwrap.dedent("""\
            x = 1

            def stub_func():
                pass
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].line == 3

    def test_nested_function_stub_flagged(self):
        """Stub nested inside a real function should be flagged."""
        source = textwrap.dedent("""\
            def outer():
                def inner():
                    pass
                return inner()
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "inner"

    # ------------------------------------------------------------------
    # Severity field — original patterns must remain ``severity="error"``.
    # Regression coverage so a future change cannot silently downgrade
    # them. See task: "Make sure to not break existing tests by changing
    # the severity of ALREADY-detected patterns."
    # ------------------------------------------------------------------

    def test_pass_only_function_severity_is_error(self):
        """Regression: ``def foo(): pass`` is still flagged at error severity."""
        source = textwrap.dedent("""\
            def foo():
                pass
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].severity == "error"

    def test_ellipsis_severity_is_error(self):
        source = textwrap.dedent("""\
            def bar():
                ...
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].severity == "error"

    def test_raise_not_implemented_severity_is_error(self):
        source = textwrap.dedent("""\
            def baz():
                raise NotImplementedError("todo")
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].severity == "error"


# ============================================================
# Warning-severity heuristics for trivial-return stubs
# ============================================================


class TestWarningStubHeuristics:
    """Step: catch trivial-return bypasses (``return 0``, ``return None``, ...).

    These are softer signals than the ``pass`` / ``...`` /
    ``raise NotImplementedError`` patterns — a function genuinely returning
    a literal can be valid — so they are reported at ``severity="warning"``.
    """

    def test_compute_returning_zero_is_warning(self):
        """``def compute(): return 0`` is a heuristic stub (warning)."""
        source = textwrap.dedent("""\
            def compute():
                return 0
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "compute"
        assert findings[0].severity == "warning"
        # Reason should call out the computation-name heuristic.
        assert "computation" in findings[0].reason.lower()

    def test_parse_returning_none_is_warning(self):
        """``def parse(x): return None`` is a heuristic stub (warning)."""
        source = textwrap.dedent("""\
            def parse(x):
                return None
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "parse"
        assert findings[0].severity == "warning"

    def test_compute_underscore_prefix_returning_empty_dict_is_warning(self):
        """The computation-name heuristic also matches ``compute_x``-style names."""
        source = textwrap.dedent("""\
            def compute_score():
                return {}
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert len(findings) == 1
        assert findings[0].function_name == "compute_score"
        assert findings[0].severity == "warning"

    def test_real_call_return_not_flagged(self):
        """``def regular_func(): return computed_value()`` is NOT flagged.

        Returning the result of a function call (not a literal) means real
        work is happening, so neither the literal-return nor the
        computation-name heuristic should fire.
        """
        source = textwrap.dedent("""\
            def regular_func():
                return computed_value()
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert findings == []

    def test_compute_with_real_call_not_flagged(self):
        """A computation-named function returning a real call is NOT flagged."""
        source = textwrap.dedent("""\
            def compute():
                return real_helper(42)
        """)
        findings = detect_stub_functions(source, "src/example.py")
        assert findings == []

    def test_return_self_attr_unassigned_is_warning(self):
        """``return self.x`` where ``self.x`` is never assigned is a warning."""
        source = textwrap.dedent("""\
            class Thing:
                def get_value(self):
                    return self.value
        """)
        findings = detect_stub_functions(source, "src/example.py")
        # ``get_value`` returns ``self.value`` but no ``self.value = ...``
        # exists in the class — heuristic fires.
        assert len(findings) >= 1
        get_value_findings = [f for f in findings if f.function_name == "get_value"]
        assert len(get_value_findings) == 1
        assert get_value_findings[0].severity == "warning"
        # All findings here should be warnings (no error stubs).
        assert all(f.severity == "warning" for f in findings)

    def test_return_self_attr_assigned_elsewhere_not_flagged(self):
        """``return self.x`` is fine when ``self.x`` is assigned somewhere."""
        source = textwrap.dedent("""\
            class Thing:
                def __init__(self, v):
                    self.value = v

                def get_value(self):
                    return self.value
        """)
        findings = detect_stub_functions(source, "src/example.py")
        # ``__init__`` is not a stub (it has a real assignment), and
        # ``get_value`` should NOT trigger the warning because
        # ``self.value`` is assigned in ``__init__``.
        assert findings == []

    def test_warning_does_not_break_passed_flag(self):
        """Heuristic warnings must NOT flip ``verify_no_stubs_or_mocks.passed``.

        The aggregator only fails verification on error-severity findings;
        otherwise legacy callers that gate on ``passed`` (or on
        ``len(result["stub_findings"]) == 0``) would suddenly start failing
        on benign ``return None`` patterns. Warnings live in a separate
        ``stub_warnings`` field for review.
        """
        sources = {
            "src/bob3/module.py": textwrap.dedent("""\
                def returns_none():
                    return None
            """),
        }
        result = verify_no_stubs_or_mocks(sources)
        assert result["passed"] is True
        # Definitive (error) stub findings stay empty so legacy callers
        # gating on this list don't suddenly fail.
        assert result["stub_findings"] == []
        # The warning is reported in the dedicated warnings list.
        assert "stub_warnings" in result
        assert len(result["stub_warnings"]) == 1
        assert result["stub_warnings"][0].severity == "warning"
        assert result["stub_warnings"][0].function_name == "returns_none"
        # Summary still surfaces the warning so a human reviewer sees it.
        assert "returns_none" in result["summary"]


# ============================================================
# STEP 7 & 8: Mock detection
# ============================================================


class TestDetectMockUsage:
    """Test detection of mock imports and usage in source files."""

    def test_mock_import_in_src_flagged(self):
        """Step 7: Mock imports in src/ should be flagged."""
        source = textwrap.dedent("""\
            from unittest.mock import MagicMock, patch

            def something():
                return 42
        """)
        findings = detect_mock_usage(source, "src/bob3/mymodule.py")
        assert len(findings) >= 1
        assert any("unittest.mock" in f.reason for f in findings)

    def test_mock_import_in_tests_allowed(self):
        """Step 8: Mock imports in tests/ should be allowed."""
        source = textwrap.dedent("""\
            from unittest.mock import MagicMock, patch

            def test_something():
                mock = MagicMock()
                assert mock is not None
        """)
        findings = detect_mock_usage(source, "tests/test_something.py")
        assert len(findings) == 0

    def test_magicmock_usage_in_src_flagged(self):
        """MagicMock usage in src/ should be flagged."""
        source = textwrap.dedent("""\
            from unittest.mock import MagicMock

            mock_obj = MagicMock()
        """)
        findings = detect_mock_usage(source, "src/bob3/bad.py")
        assert len(findings) >= 1

    def test_from_mock_import_in_src_flagged(self):
        """'from mock import ...' in src/ should be flagged."""
        source = textwrap.dedent("""\
            from mock import Mock, patch
        """)
        findings = detect_mock_usage(source, "src/bob3/bad.py")
        assert len(findings) >= 1

    def test_import_mock_in_src_flagged(self):
        """'import mock' in src/ should be flagged."""
        source = textwrap.dedent("""\
            import mock
        """)
        findings = detect_mock_usage(source, "src/bob3/bad.py")
        assert len(findings) >= 1

    def test_import_unittest_mock_in_src_flagged(self):
        """'import unittest.mock' in src/ should be flagged."""
        source = textwrap.dedent("""\
            import unittest.mock
        """)
        findings = detect_mock_usage(source, "src/bob3/bad.py")
        assert len(findings) >= 1

    def test_no_mock_usage_clean(self):
        """Normal source with no mock usage should return empty."""
        source = textwrap.dedent("""\
            import os
            import json

            def clean_function():
                return json.dumps({"key": "value"})
        """)
        findings = detect_mock_usage(source, "src/bob3/clean.py")
        assert len(findings) == 0

    def test_invalid_syntax_returns_empty(self):
        """Invalid Python source should not crash for mock detection."""
        source = "from unittest.mock import \n  broken("
        findings = detect_mock_usage(source, "src/broken.py")
        assert findings == []


# ============================================================
# STEP 4: Integration into verification checklist
# ============================================================


class TestVerifyNoStubsOrMocks:
    """Test the combined verification function."""

    def test_clean_source_passes(self):
        """Clean source with real implementations passes.

        Use a body that performs computation on its arguments — the
        literal-return heuristic does not match because the return value
        is not a literal, so no warning fires either.
        """
        sources = {
            "src/bob3/module.py": textwrap.dedent("""\
                def real_func(a, b):
                    return a + b
            """),
        }
        result = verify_no_stubs_or_mocks(sources)
        assert result["passed"] is True
        assert result["stub_findings"] == []
        assert result["mock_findings"] == []

    def test_stub_in_src_fails(self):
        """Stub function in src/ fails verification."""
        sources = {
            "src/bob3/module.py": textwrap.dedent("""\
                def stub_func():
                    pass
            """),
        }
        result = verify_no_stubs_or_mocks(sources)
        assert result["passed"] is False
        assert len(result["stub_findings"]) == 1

    def test_mock_in_src_fails(self):
        """Mock usage in src/ fails verification."""
        sources = {
            "src/bob3/module.py": textwrap.dedent("""\
                from unittest.mock import MagicMock
                x = MagicMock()
            """),
        }
        result = verify_no_stubs_or_mocks(sources)
        assert result["passed"] is False
        assert len(result["mock_findings"]) >= 1

    def test_mock_in_tests_passes(self):
        """Mock usage in tests/ passes verification (allowed)."""
        sources = {
            "tests/test_foo.py": textwrap.dedent("""\
                from unittest.mock import MagicMock
                def test_foo():
                    m = MagicMock()
                    assert m is not None
            """),
        }
        result = verify_no_stubs_or_mocks(sources)
        assert result["passed"] is True
        assert result["mock_findings"] == []

    def test_mixed_findings(self):
        """Both stubs and mocks in src/ are reported."""
        sources = {
            "src/bob3/a.py": textwrap.dedent("""\
                def stub():
                    pass
            """),
            "src/bob3/b.py": textwrap.dedent("""\
                from unittest.mock import Mock
            """),
        }
        result = verify_no_stubs_or_mocks(sources)
        assert result["passed"] is False
        assert len(result["stub_findings"]) == 1
        assert len(result["mock_findings"]) >= 1

    def test_summary_format(self):
        """Result should contain a human-readable summary."""
        sources = {
            "src/bob3/module.py": textwrap.dedent("""\
                def foo():
                    ...
            """),
        }
        result = verify_no_stubs_or_mocks(sources)
        assert "summary" in result
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

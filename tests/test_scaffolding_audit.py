"""Tests for scaffolding_audit.py - audit_diff function.

Tests verify that audit_diff correctly identifies compensatory code patterns
(try/except that swallows, return inside except without re-raise, pass inside
except, if-not-thing-return guards) in newly added lines of a diff, and
reports violations when such patterns lack a # SCAFFOLDING(<reason>) comment.
"""

from __future__ import annotations

import pytest

from bob3.scaffolding_audit import ScaffoldingViolation, audit_diff


# ---------------------------------------------------------------------------
# Helper: build a minimal unified diff string
# ---------------------------------------------------------------------------

def _make_diff(old_lines: list[str], new_lines: list[str], filename: str = "foo.py") -> str:
    """Create a minimal unified diff string from old and new lines."""
    header = f"--- a/{filename}\n+++ b/{filename}\n"
    hunk_header = f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@\n"
    hunk_body = ""
    for line in old_lines:
        hunk_body += f"-{line}\n"
    for line in new_lines:
        hunk_body += f"+{line}\n"
    return header + hunk_header + hunk_body


def _added_only(new_lines: list[str], filename: str = "foo.py") -> str:
    """Create a diff where all given lines are added."""
    header = f"--- a/{filename}\n+++ b/{filename}\n"
    hunk_header = f"@@ -0,0 +1,{len(new_lines)} @@\n"
    hunk_body = "".join(f"+{line}\n" for line in new_lines)
    return header + hunk_header + hunk_body


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_list(self):
        result = audit_diff("")
        assert isinstance(result, list)

    def test_empty_diff_returns_empty_list(self):
        assert audit_diff("") == []

    def test_clean_diff_returns_empty_list(self):
        diff = _added_only(["def foo():", "    return 42"])
        assert audit_diff(diff) == []

    def test_violation_is_scaffolding_violation(self):
        diff = _added_only([
            "try:",
            "    x = risky()",
            "except Exception:",
            "    pass",
        ])
        result = audit_diff(diff)
        assert len(result) >= 1
        assert all(isinstance(v, ScaffoldingViolation) for v in result)


# ---------------------------------------------------------------------------
# ScaffoldingViolation dataclass fields
# ---------------------------------------------------------------------------

class TestScaffoldingViolationFields:
    def test_has_line_number(self):
        diff = _added_only([
            "try:",
            "    x = risky()",
            "except Exception:",
            "    pass",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1
        assert hasattr(violations[0], "line")
        assert isinstance(violations[0].line, int)

    def test_has_reason_field(self):
        diff = _added_only([
            "try:",
            "    x = risky()",
            "except Exception:",
            "    pass",
        ])
        violations = audit_diff(diff)
        assert hasattr(violations[0], "reason")
        assert isinstance(violations[0].reason, str)

    def test_has_code_field(self):
        diff = _added_only([
            "try:",
            "    x = risky()",
            "except Exception:",
            "    pass",
        ])
        violations = audit_diff(diff)
        assert hasattr(violations[0], "code")
        assert isinstance(violations[0].code, str)


# ---------------------------------------------------------------------------
# Pattern: pass inside except (no re-raise)
# ---------------------------------------------------------------------------

class TestPassInsideExcept:
    def test_pass_in_except_is_violation(self):
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception:",
            "    pass",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1

    def test_pass_in_except_with_scaffolding_comment_same_line(self):
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception:",
            "    pass  # SCAFFOLDING(safe to ignore here)",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_pass_in_except_with_scaffolding_comment_preceding_line(self):
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception:",
            "    # SCAFFOLDING(not critical path)",
            "    pass",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_pass_outside_except_is_not_violation(self):
        diff = _added_only([
            "if True:",
            "    pass",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_pass_in_except_specific_exception(self):
        diff = _added_only([
            "try:",
            "    risky()",
            "except ValueError:",
            "    pass",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# Pattern: return inside except without re-raise
# ---------------------------------------------------------------------------

class TestReturnInsideExcept:
    def test_return_in_except_without_reraise_is_violation(self):
        diff = _added_only([
            "try:",
            "    result = compute()",
            "except Exception:",
            "    return None",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1

    def test_return_default_value_in_except_is_violation(self):
        diff = _added_only([
            "try:",
            "    result = compute()",
            "except Exception:",
            "    return []",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1

    def test_return_in_except_with_scaffolding_same_line(self):
        diff = _added_only([
            "try:",
            "    result = compute()",
            "except Exception:",
            "    return None  # SCAFFOLDING(caller handles None)",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_return_in_except_with_scaffolding_preceding_line(self):
        diff = _added_only([
            "try:",
            "    result = compute()",
            "except Exception:",
            "    # SCAFFOLDING(default is acceptable here)",
            "    return None",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_reraise_in_except_is_not_violation(self):
        diff = _added_only([
            "try:",
            "    result = compute()",
            "except Exception:",
            "    raise",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_raise_new_exception_in_except_is_not_violation(self):
        diff = _added_only([
            "try:",
            "    result = compute()",
            "except ValueError as e:",
            "    raise RuntimeError('wrapped') from e",
        ])
        violations = audit_diff(diff)
        assert violations == []


# ---------------------------------------------------------------------------
# Pattern: try/except that swallows (logs + continues, no re-raise)
# ---------------------------------------------------------------------------

class TestSwallowingExcept:
    def test_log_and_continue_is_violation(self):
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception as e:",
            "    logger.error(e)",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1

    def test_log_and_continue_with_scaffolding_is_ok(self):
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception as e:",
            "    logger.error(e)  # SCAFFOLDING(non-critical, log and continue)",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_except_with_assignment_default_is_violation(self):
        diff = _added_only([
            "try:",
            "    value = parse(x)",
            "except Exception:",
            "    value = 'default'",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1

    def test_except_with_assignment_and_scaffolding_is_ok(self):
        diff = _added_only([
            "try:",
            "    value = parse(x)",
            "except Exception:",
            "    value = 'default'  # SCAFFOLDING(graceful fallback)",
        ])
        violations = audit_diff(diff)
        assert violations == []


# ---------------------------------------------------------------------------
# Pattern: if not <thing>: return guard
# ---------------------------------------------------------------------------

class TestIfNotGuard:
    def test_if_not_x_return_is_violation(self):
        diff = _added_only([
            "if not data:",
            "    return",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1

    def test_if_not_x_return_value_is_violation(self):
        diff = _added_only([
            "if not config:",
            "    return None",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1

    def test_if_not_x_return_with_scaffolding_same_line(self):
        diff = _added_only([
            "if not data:  # SCAFFOLDING(data is optional)",
            "    return",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_if_not_x_return_with_scaffolding_preceding_line(self):
        diff = _added_only([
            "# SCAFFOLDING(data may be empty on first run)",
            "if not data:",
            "    return",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_if_x_return_without_not_is_not_violation(self):
        # "if x: return" is not the compensatory guard pattern
        diff = _added_only([
            "if found:",
            "    return found",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_if_not_x_with_body_not_just_return_is_not_violation(self):
        diff = _added_only([
            "if not data:",
            "    log_missing()",
            "    return",
        ])
        violations = audit_diff(diff)
        # multi-statement body — not a simple guard
        assert violations == []


# ---------------------------------------------------------------------------
# SCAFFOLDING comment variations
# ---------------------------------------------------------------------------

class TestScaffoldingCommentVariants:
    def test_scaffolding_with_empty_reason_is_valid(self):
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception:",
            "    pass  # SCAFFOLDING()",
        ])
        violations = audit_diff(diff)
        assert violations == []

    def test_partial_scaffolding_comment_not_matched(self):
        # "SCAFFOLD" without the full tag does not count
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception:",
            "    pass  # SCAFFOLD(reason)",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1

    def test_scaffolding_tag_case_sensitive(self):
        # lowercase scaffolding does not count
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception:",
            "    pass  # scaffolding(reason)",
        ])
        violations = audit_diff(diff)
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# Diff context: only NEW lines are checked
# ---------------------------------------------------------------------------

class TestOnlyNewLinesChecked:
    def test_removed_lines_not_flagged(self):
        # A compensatory pattern that was removed (- lines) should not trigger
        diff = (
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,4 +1,1 @@\n"
            "-try:\n"
            "-    risky()\n"
            "-except Exception:\n"
            "-    pass\n"
            "+x = 1\n"
        )
        violations = audit_diff(diff)
        assert violations == []

    def test_context_lines_not_flagged(self):
        # Context lines (no prefix) containing compensatory code are not new
        diff = (
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,5 +1,6 @@\n"
            " try:\n"
            "     risky()\n"
            " except Exception:\n"
            "     pass\n"
            "+x = 1\n"
        )
        violations = audit_diff(diff)
        assert violations == []

    def test_only_added_lines_with_pattern_flagged(self):
        diff = (
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,1 +1,5 @@\n"
            " x = 1\n"
            "+try:\n"
            "+    risky()\n"
            "+except Exception:\n"
            "+    pass\n"
        )
        violations = audit_diff(diff)
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# Multi-hunk diffs
# ---------------------------------------------------------------------------

class TestMultiHunkDiffs:
    def test_violations_across_multiple_hunks(self):
        diff = (
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,1 +1,4 @@\n"
            " x = 1\n"
            "+try:\n"
            "+    risky()\n"
            "+except Exception:\n"
            "+    pass\n"
            "@@ -10,1 +13,4 @@\n"
            " y = 2\n"
            "+try:\n"
            "+    other()\n"
            "+except Exception:\n"
            "+    return None\n"
        )
        violations = audit_diff(diff)
        assert len(violations) >= 2

    def test_clean_hunk_mixed_with_violating_hunk(self):
        diff = (
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,1 +1,2 @@\n"
            " x = 1\n"
            "+y = 2\n"
            "@@ -10,1 +11,4 @@\n"
            " z = 3\n"
            "+try:\n"
            "+    risky()\n"
            "+except Exception:\n"
            "+    pass\n"
        )
        violations = audit_diff(diff)
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# Non-Python files
# ---------------------------------------------------------------------------

class TestNonPythonFiles:
    def test_non_python_file_not_flagged(self):
        diff = (
            "--- a/config.yaml\n"
            "+++ b/config.yaml\n"
            "@@ -0,0 +1,4 @@\n"
            "+try:\n"
            "+    risky()\n"
            "+except:\n"
            "+    pass\n"
        )
        violations = audit_diff(diff)
        assert violations == []

    def test_python_file_extension_flagged(self):
        diff = _added_only([
            "try:",
            "    risky()",
            "except Exception:",
            "    pass",
        ], filename="module/submod.py")
        violations = audit_diff(diff)
        assert len(violations) >= 1

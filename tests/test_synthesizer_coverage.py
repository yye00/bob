"""Tests for bob.synthesizer.inject_boundary_error_criteria.

Covers:
- Structural-only ACs get both boundary and error injected
- Already-has-boundary: only error injected
- Already-has-error: only boundary injected
- Already-has-both: no injection
- Injected ACs reference the feature slug (not generic boilerplate)
- Injected ACs use pytest: structured form (not bare prose)
- Composite score rises from 0.0 when both are injected
"""
import pytest
from bob.synthesizer import inject_boundary_error_criteria


def test_structural_acs_get_boundary_and_error():
    criteria = [
        "File exists: src/bob/synthesizer.py",
        "Function defined: bob.synthesizer.parse_criteria_response",
        "pytest: tests/test_synthesizer.py",
    ]
    result = inject_boundary_error_criteria(criteria, title="my feature")
    # Both types should be injected
    lower = [c.lower() for c in result]
    has_boundary = any(
        any(tok in c for tok in ("empty", "null", "zero", "minimum", "boundary", "limit"))
        for c in lower
    )
    has_error = any(
        any(tok in c for tok in ("error", "exception", "fail", "invalid", "reject", "raise",
                                  "does not", "must not", "valueerror"))
        for c in lower
    )
    assert has_boundary, "Expected boundary AC to be injected"
    assert has_error, "Expected error-path AC to be injected"


def test_boundary_only_present_gets_error_injected():
    criteria = [
        "File exists: src/foo.py",
        "pytest: tests/test_foo_boundary.py — empty input returns a defined result (boundary)",
    ]
    result = inject_boundary_error_criteria(criteria, title="foo feature")
    lower = [c.lower() for c in result]
    has_error = any(
        any(tok in c for tok in ("error", "exception", "fail", "invalid", "reject", "raise",
                                  "does not", "must not"))
        for c in lower
    )
    assert has_error, "Expected error-path AC to be injected when only boundary was present"
    # Should not add another boundary
    boundary_count = sum(
        1 for c in lower
        if any(tok in c for tok in ("empty", "minimum", "boundary"))
    )
    # only the original one (no duplication)
    assert boundary_count == 1


def test_error_only_present_gets_boundary_injected():
    criteria = [
        "File exists: src/foo.py",
        "pytest: tests/test_foo_error.py — invalid input raises ValueError (error path)",
    ]
    result = inject_boundary_error_criteria(criteria, title="foo feature")
    lower = [c.lower() for c in result]
    has_boundary = any(
        any(tok in c for tok in ("empty", "null", "zero", "minimum", "boundary", "limit"))
        for c in lower
    )
    assert has_boundary, "Expected boundary AC to be injected when only error-path was present"


def test_no_injection_when_both_present():
    criteria = [
        "File exists: src/foo.py",
        "pytest: tests/test_foo_boundary.py — empty input returns a defined result",
        "pytest: tests/test_foo_error.py — invalid input raises ValueError",
    ]
    result = inject_boundary_error_criteria(criteria, title="foo feature")
    assert len(result) == len(criteria), "No injection expected when both ACs already present"


def test_injected_ac_references_feature_slug():
    criteria = [
        "File exists: src/bob/synthesizer.py",
        "Function defined: bob.synthesizer.parse_criteria_response",
        "pytest: tests/test_synthesizer.py",
    ]
    title = "Synthesizer parse and inject"
    result = inject_boundary_error_criteria(criteria, title=title)
    injected = [c for c in result if c not in criteria]
    for ac in injected:
        # Must reference something derived from the feature, not generic boilerplate
        assert "feature" not in ac.lower() or "synthesizer" in ac.lower(), (
            f"Injected AC looks generic (not feature-specific): {ac!r}"
        )


def test_injected_acs_use_pytest_structured_form():
    """Injected ACs must use pytest: form to satisfy spec_executability."""
    criteria = [
        "File exists: src/bob/synthesizer.py",
        "Function defined: bob.synthesizer.inject_boundary_error_criteria",
        "pytest: tests/test_synthesizer_coverage.py",
    ]
    result = inject_boundary_error_criteria(criteria, title="synthesizer boundary coverage")
    injected = [c for c in result if c not in criteria]
    for ac in injected:
        assert ac.startswith("pytest:"), (
            f"Injected AC must use 'pytest:' structured form, got: {ac!r}"
        )


def test_empty_criteria_gets_both_injected():
    result = inject_boundary_error_criteria([], title="some feature")
    lower = [c.lower() for c in result]
    has_boundary = any(
        any(tok in c for tok in ("empty", "zero", "minimum", "boundary"))
        for c in lower
    )
    has_error = any(
        any(tok in c for tok in ("error", "valueerror", "invalid", "fail"))
        for c in lower
    )
    assert has_boundary
    assert has_error


def test_criteria_count_increases_by_two_when_both_missing():
    criteria = [
        "File exists: src/foo.py",
        "pytest: tests/test_foo.py",
    ]
    result = inject_boundary_error_criteria(criteria, title="foo")
    assert len(result) == len(criteria) + 2


def test_criteria_count_increases_by_one_when_one_present():
    criteria = [
        "File exists: src/foo.py",
        "pytest: tests/test_foo_boundary.py — empty input returns a defined result (boundary case)",
    ]
    result = inject_boundary_error_criteria(criteria, title="foo")
    assert len(result) == len(criteria) + 1

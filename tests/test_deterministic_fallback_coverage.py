"""F-R7-625 follow-up: deterministic_fallback MUST carry boundary + error-path ACs.

After fixing the LLM synthesis path to inject boundary + error-path ACs, rate-
limited features still scored 0.0 because deterministic_fallback emitted only 3
structural ACs (File exists / pytest / Function defined) with NO boundary or
error-path AC.  The composite spec_quality_score is a weighted geometric mean,
so boundary_coverage=0 AND error_path_coverage=0 force composite=0.0 → feature
re-blocks at the 0.85 gate.

This test file pins that _ensure_boundary_and_error_coverage is applied to the
deterministic_fallback output so EITHER path (live LLM synthesis or fallback)
yields gate-passing ACs.
"""
from __future__ import annotations

import re

import pytest

from bob.spec_synthesizer import (
    _ensure_boundary_and_error_coverage,
    deterministic_fallback,
    deterministic_fallback_spec,
)

# ── Boundary keyword regex (same as the scorer) ──────────────────────────────
_BND = re.compile(
    r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
    r"boundary|edge case|corner case|overflow|underflow|limit|"
    r"threshold|floor|ceiling)\b",
    re.IGNORECASE,
)

# ── Error keyword regex (same as the scorer) ─────────────────────────────────
_ERR = re.compile(
    r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
    r"block|does not|cannot|must not|shall not|ValueError|KeyError|"
    r"TypeError|RuntimeError)\b",
    re.IGNORECASE,
)


def _has_boundary_ac(criteria: list[str]) -> bool:
    """Return True iff at least one AC contains a boundary keyword."""
    return any(_BND.search(c) for c in criteria)


def _has_error_ac(criteria: list[str]) -> bool:
    """Return True iff at least one AC contains an error keyword."""
    return any(_ERR.search(c) for c in criteria)


# ── Core coverage guarantees ─────────────────────────────────────────────────


class TestDeterministicFallbackCarriesCoverage:
    """deterministic_fallback must emit boundary + error ACs so the composite
    spec_quality_score can exceed 0.0 even without LLM synthesis."""

    def test_fallback_includes_boundary_ac(self):
        criteria = deterministic_fallback(
            "rate limiter",
            "Enforce a per-key request rate limit.",
        )
        assert _has_boundary_ac(criteria), (
            f"No boundary AC in fallback output: {criteria}"
        )

    def test_fallback_includes_error_ac(self):
        criteria = deterministic_fallback(
            "rate limiter",
            "Enforce a per-key request rate limit.",
        )
        assert _has_error_ac(criteria), (
            f"No error-path AC in fallback output: {criteria}"
        )

    def test_fallback_includes_both_boundary_and_error(self):
        criteria = deterministic_fallback(
            "config validator",
            "Validate incoming configuration dictionaries.",
        )
        assert _has_boundary_ac(criteria), criteria
        assert _has_error_ac(criteria), criteria

    def test_fallback_boundary_ac_uses_pytest_form(self):
        """The injected boundary AC must use the pytest: structured form so it
        satisfies spec_executability, traceability, AND boundary_coverage."""
        criteria = deterministic_fallback("job scheduler", "Schedule deferred jobs.")
        boundary_acs = [c for c in criteria if _BND.search(c)]
        assert boundary_acs, criteria
        assert any(c.lower().startswith("pytest:") for c in boundary_acs), (
            f"Boundary AC must use pytest: form: {boundary_acs}"
        )

    def test_fallback_error_ac_uses_pytest_form(self):
        """The injected error-path AC must use the pytest: structured form."""
        criteria = deterministic_fallback("job scheduler", "Schedule deferred jobs.")
        error_acs = [c for c in criteria if _ERR.search(c)]
        assert error_acs, criteria
        assert any(c.lower().startswith("pytest:") for c in error_acs), (
            f"Error-path AC must use pytest: form: {error_acs}"
        )

    def test_fallback_coverage_for_multiple_titles(self):
        titles = [
            ("budget tracker", "Track expenses."),
            ("metrics emitter", "Emit usage metrics."),
            ("cache eviction", "Evict stale entries from cache."),
            ("token refresher", "Refresh expired auth tokens."),
        ]
        for name, desc in titles:
            criteria = deterministic_fallback(name, desc)
            assert _has_boundary_ac(criteria), (
                f"No boundary AC for {name!r}: {criteria}"
            )
            assert _has_error_ac(criteria), (
                f"No error-path AC for {name!r}: {criteria}"
            )


class TestDeterministicFallbackSpecCarriesCoverage:
    """deterministic_fallback_spec (dict-returning sibling) must also satisfy
    the coverage guarantee so callers that use the structured form are not
    left with a composite-0.0 spec."""

    def test_spec_dict_includes_boundary_ac(self):
        spec = deterministic_fallback_spec(
            "result cache",
            "An in-memory LRU cache.",
        )
        criteria = spec["acceptance_criteria"]
        assert _has_boundary_ac(criteria), criteria

    def test_spec_dict_includes_error_ac(self):
        spec = deterministic_fallback_spec(
            "result cache",
            "An in-memory LRU cache.",
        )
        criteria = spec["acceptance_criteria"]
        assert _has_error_ac(criteria), criteria


# ── _ensure_boundary_and_error_coverage stand-alone tests ────────────────────


class TestEnsureBoundaryAndErrorCoverage:
    """Unit tests for the underlying injector so its invariants are pinned
    independently of deterministic_fallback."""

    def test_injects_boundary_ac_when_absent(self):
        criteria = ["File exists: src/bob/foo.py", "pytest: tests/test_foo.py"]
        out = _ensure_boundary_and_error_coverage(criteria, title="foo")
        assert _has_boundary_ac(out), out

    def test_injects_error_ac_when_absent(self):
        criteria = ["File exists: src/bob/foo.py", "pytest: tests/test_foo.py"]
        out = _ensure_boundary_and_error_coverage(criteria, title="foo")
        assert _has_error_ac(out), out

    def test_does_not_duplicate_existing_boundary_ac(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty input returns None",
            "pytest: tests/test_foo.py",
        ]
        out = _ensure_boundary_and_error_coverage(criteria, title="foo")
        boundary_acs = [c for c in out if _BND.search(c)]
        # Should not add a second boundary AC when one already exists.
        assert len(boundary_acs) == 1, (
            f"Duplicate boundary AC injected: {out}"
        )

    def test_does_not_duplicate_existing_error_ac(self):
        criteria = [
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
            "pytest: tests/test_foo.py",
        ]
        out = _ensure_boundary_and_error_coverage(criteria, title="foo")
        error_acs = [c for c in out if _ERR.search(c)]
        assert len(error_acs) == 1, (
            f"Duplicate error AC injected: {out}"
        )

    def test_injects_nothing_when_both_already_present(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty input returns None",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
            "File exists: src/bob/foo.py",
        ]
        out = _ensure_boundary_and_error_coverage(criteria, title="foo")
        assert len(out) == len(criteria), (
            f"Unexpected injection when both already present: {out}"
        )

    def test_injected_ac_references_title_slug(self):
        out = _ensure_boundary_and_error_coverage(
            ["File exists: src/bob/budget_tracker.py"],
            title="budget tracker",
        )
        boundary_acs = [c for c in out if _BND.search(c)]
        assert boundary_acs, out
        # The slug derived from the title should appear in the AC path.
        assert "budget_tracker" in boundary_acs[0], boundary_acs

    def test_empty_criteria_list_gets_both_injected(self):
        out = _ensure_boundary_and_error_coverage([], title="event emitter")
        assert _has_boundary_ac(out), out
        assert _has_error_ac(out), out

    def test_boundary_ac_keyword_in_injected_content(self):
        out = _ensure_boundary_and_error_coverage(
            ["File exists: src/bob/foo.py"],
            title="foo",
        )
        boundary_acs = [c for c in out if _BND.search(c)]
        assert boundary_acs, out
        # Verify a real boundary keyword is present, not just the slug.
        lower = boundary_acs[0].lower()
        assert any(kw in lower for kw in ("empty", "zero", "minimum", "boundary")), (
            f"Injected boundary AC missing expected keyword: {boundary_acs[0]}"
        )

    def test_error_ac_keyword_in_injected_content(self):
        out = _ensure_boundary_and_error_coverage(
            ["File exists: src/bob/foo.py"],
            title="foo",
        )
        error_acs = [c for c in out if _ERR.search(c)]
        assert error_acs, out
        lower = error_acs[0].lower()
        assert any(kw in lower for kw in ("error", "invalid", "raise", "valueerror")), (
            f"Injected error AC missing expected keyword: {error_acs[0]}"
        )


# ── Integration: both paths yield composite > 0.0 ────────────────────────────


class TestCompositeSurvivesRateLimit:
    """Simulate the rate-limit scenario: when the LLM is unavailable, the
    fallback path must produce ACs that prevent boundary_coverage=0 and
    error_path_coverage=0, which would zero the geometric mean."""

    def test_fallback_does_not_produce_zero_composite_inputs(self):
        """Verify the fallback output has at least one boundary and one error AC,
        which are the exact conditions that forced composite=0.0."""
        criteria = deterministic_fallback(
            "feature x",
            "Some feature that may be rate-limited.",
        )
        assert _has_boundary_ac(criteria), (
            "Rate-limit fallback would produce boundary_coverage=0 → composite=0.0"
        )
        assert _has_error_ac(criteria), (
            "Rate-limit fallback would produce error_path_coverage=0 → composite=0.0"
        )

    def test_structural_only_acs_would_fail_composite(self):
        """Document the anti-pattern: 3 structural ACs alone would zero the mean."""
        structural_only = [
            "File exists: src/bob/feature_x.py",
            "pytest: tests/test_feature_x.py::test_feature_x",
            "Function defined: bob.feature_x.feature_x",
        ]
        # Without boundary/error keywords, composite sub-metrics would be 0.
        assert not _has_boundary_ac(structural_only), (
            "Test assumption violated: structural ACs should not have boundary keywords"
        )
        assert not _has_error_ac(structural_only), (
            "Test assumption violated: structural ACs should not have error keywords"
        )
        # After applying the guarantee, both are present.
        enriched = _ensure_boundary_and_error_coverage(structural_only, title="feature_x")
        assert _has_boundary_ac(enriched)
        assert _has_error_ac(enriched)

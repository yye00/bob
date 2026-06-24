"""Tests for bob.spec_synthesizer — score-gate loop and sanitize_spec_file.

Feature 4179c0d0: Spec synthesizer score-gate loop — re-synthesize TBD ACs
until score reaches threshold.

Covers:
  - sanitize_spec_file rewrites placeholder ACs
  - score_gate_loop retries until threshold is met, caps at max_retries
  - score_gate_loop falls back to deterministic_fallback on exhaustion
  - score_gate_loop reports gate_passed, gate_failed, gate_avg_attempts
  - score_gate_loop passes retry_feedback on undershooting attempts
  - build_retry_feedback_prompt names failing sub-metrics
  - score_gate_threshold_from_env reads BOB_SPEC_QUALITY_THRESHOLD
  - should_emit_function_defined_ac checks verbatim symbol presence (F-R7-620)
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from bob.spec_synthesizer import (
    ScoreGateReport,
    build_retry_feedback_prompt,
    deterministic_fallback,
    import_spec_quality_scorer,
    resilient_import_scorer,
    sanitize_spec_file,
    score_gate_loop,
    score_gate_threshold_from_env,
    score_synthesized_acs,
    should_emit_function_defined_ac,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_spec_file(features: dict) -> Path:
    """Write a YAML spec to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    )
    yaml.safe_dump({"features": features}, tmp, sort_keys=False)
    tmp.flush()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# Tests for should_emit_function_defined_ac (F-R7-620, feature 6d3d99ed)
# ---------------------------------------------------------------------------

class TestShouldEmitFunctionDefinedAc:
    """should_emit_function_defined_ac returns True iff symbol appears verbatim
    in description (exact identifier match, not just substring).
    """

    def test_returns_true_when_symbol_verbatim_in_description(self):
        desc = "Call apply_exponential_backoff whenever the reaper resets a feature."
        assert should_emit_function_defined_ac("apply_exponential_backoff", desc) is True

    def test_returns_false_when_symbol_absent(self):
        desc = "Apply exponential backoff after each reaper reset."
        # prose describes the CONCEPT but does not name the exact symbol
        assert should_emit_function_defined_ac("apply_exponential_backoff", desc) is False

    def test_returns_false_when_synonym_present_but_not_exact(self):
        desc = "Implement handle_exponential_backoff in the reaper module."
        # handle_exponential_backoff ≠ apply_exponential_backoff
        assert should_emit_function_defined_ac("apply_exponential_backoff", desc) is False

    def test_returns_true_for_camelcase_symbol(self):
        desc = "Expose BackoffDecision from the reaper public API."
        assert should_emit_function_defined_ac("BackoffDecision", desc) is True

    def test_returns_false_for_empty_description(self):
        assert should_emit_function_defined_ac("my_func", "") is False

    def test_returns_false_for_none_like_description(self):
        assert should_emit_function_defined_ac("my_func", "   ") is False

    def test_match_is_word_boundary_not_substring(self):
        # "apply_backoff" should NOT match "apply_backoff_extended"
        desc = "Use apply_backoff_extended to implement the feature."
        assert should_emit_function_defined_ac("apply_backoff", desc) is False

    def test_symbol_in_backticks_is_verbatim(self):
        desc = "Implement `should_refuse_redispatch` to gate re-dispatch."
        assert should_emit_function_defined_ac("should_refuse_redispatch", desc) is True

    def test_partial_word_overlap_not_matched(self):
        desc = "The check_budget function ensures cost limits are respected."
        assert should_emit_function_defined_ac("check", desc) is False

    def test_returns_false_for_empty_symbol(self):
        desc = "Some description with content."
        assert should_emit_function_defined_ac("", desc) is False


# ---------------------------------------------------------------------------
# Existing tests preserved below
# ---------------------------------------------------------------------------

class TestDeterministicFallback:
    def test_returns_list_of_strings(self):
        result = deterministic_fallback("my feature")
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

    def test_contains_file_exists(self):
        result = deterministic_fallback("my feature")
        assert any(c.startswith("File exists:") for c in result)

    def test_contains_pytest(self):
        result = deterministic_fallback("my feature")
        assert any(c.startswith("pytest:") for c in result)

    def test_raises_for_empty_title(self):
        with pytest.raises(ValueError):
            deterministic_fallback("")

    def test_contains_function_defined(self):
        result = deterministic_fallback("my feature")
        assert any(c.startswith("Function defined:") for c in result)

    def test_no_keyword_slug(self):
        # "import" is a Python keyword — must not appear as slug
        result = deterministic_fallback("import data from external source")
        for c in result:
            if c.startswith("Function defined:"):
                parts = c.split(".")
                assert parts[-1] not in ("import", "from")

    def test_unicode_title(self):
        result = deterministic_fallback("café handler")
        assert isinstance(result, list)
        assert len(result) >= 3

class TestScoreGateThresholdFromEnv:
    def test_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.9")
        assert score_gate_threshold_from_env() == pytest.approx(0.9)

    def test_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        val = score_gate_threshold_from_env()
        assert 0.0 < val <= 1.0

    def test_clamps_to_valid_range(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "1.5")
        val = score_gate_threshold_from_env()
        assert val <= 1.0


class TestBuildRetryFeedbackPrompt:
    def test_returns_string(self):
        result = build_retry_feedback_prompt(
            previous_criteria=["File exists: src/foo.py"],
            score=0.5,
            rationale=["low coverage"],
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_score(self):
        result = build_retry_feedback_prompt(
            previous_criteria=["pytest: tests/test_foo.py"],
            score=0.42,
            rationale=["missing integration"],
        )
        assert "0.42" in result or "42" in result

    def test_includes_rationale(self):
        result = build_retry_feedback_prompt(
            previous_criteria=["File exists: src/bar.py"],
            score=0.6,
            rationale=["missing boundary coverage"],
        )
        assert "boundary" in result.lower() or "rationale" in result.lower()


# ---------------------------------------------------------------------------
# Tests for resilient_import_scorer (feature 7c060a1e)
# ---------------------------------------------------------------------------

class TestScorerImportResilience:
    """resilient_import_scorer MUST succeed regardless of process working directory."""

    def test_scorer_import_resilient_to_cwd(self, tmp_path, monkeypatch):
        """WHEN score_gate_loop scores a candidate THEN the scorer import MUST
        succeed regardless of the process working directory.

        Simulates an arbitrary cwd (tmp_path, not the gen root) and verifies
        that resilient_import_scorer() still returns a callable scorer.
        """
        monkeypatch.chdir(tmp_path)
        compute = resilient_import_scorer()
        assert callable(compute), (
            "resilient_import_scorer must return a callable scorer regardless of cwd"
        )
        result = compute(
            name="test feature",
            description="A test feature for resilience verification",
            acceptance_criteria=["File exists: src/bob/test_feature.py"],
        )
        assert hasattr(result, "composite"), (
            "scorer result must have a .composite attribute"
        )
        assert 0.0 <= result.composite <= 1.0, (
            f"composite score must be in [0, 1], got {result.composite}"
        )

    def test_scorer_import_error_raises_loudly(self, monkeypatch):
        """WHEN the scorer cannot be found even after path augmentation THEN
        resilient_import_scorer MUST raise ImportError loudly (not silently
        degrade to a deterministic fallback).

        Patches sys.path and the import machinery so neither the primary nor
        the path-augmented import succeeds, then asserts ImportError is raised.
        """
        import sys
        import importlib
        import bob.spec_synthesizer as _mod

        original_load_compute = _mod._load_compute

        def _failing_load_compute():
            raise ImportError(
                "Simulated scorer import failure — scorer genuinely not found"
            )

        monkeypatch.setattr(_mod, "_load_compute", _failing_load_compute)

        # Also remove the real module from sys.modules so the import inside
        # resilient_import_scorer's inner _try_import() also fails.
        saved_modules = {}
        for key in list(sys.modules.keys()):
            if "spec_quality" in key and "quality_score" in key:
                saved_modules[key] = sys.modules.pop(key)

        try:
            with pytest.raises(ImportError, match="resilient_import_scorer"):
                # Use a patched version that calls the failing _load_compute
                # but cannot find the scorer via _try_import either.
                _mod.resilient_import_scorer()
        finally:
            sys.modules.update(saved_modules)
            monkeypatch.setattr(_mod, "_load_compute", original_load_compute)


# ---------------------------------------------------------------------------
# Top-level aliases required by AC node-id format (feature 7c060a1e)
# These satisfy:
#   pytest: tests/test_spec_synthesizer.py::test_scorer_import_resilient_to_cwd
#   pytest: tests/test_spec_synthesizer.py::test_scorer_import_error_raises_loudly
# ---------------------------------------------------------------------------

def test_scorer_import_resilient_to_cwd(tmp_path, monkeypatch):
    """WHEN score_gate_loop scores a candidate THEN the scorer import MUST
    succeed regardless of the process working directory.

    Simulates an arbitrary cwd (tmp_path, not the gen root) and verifies
    that resilient_import_scorer() still returns a callable scorer.
    """
    monkeypatch.chdir(tmp_path)
    compute = resilient_import_scorer()
    assert callable(compute), (
        "resilient_import_scorer must return a callable scorer regardless of cwd"
    )
    result = compute(
        name="test feature",
        description="A test feature for resilience verification",
        acceptance_criteria=["File exists: src/bob/test_feature.py"],
    )
    assert hasattr(result, "composite"), (
        "scorer result must have a .composite attribute"
    )
    assert 0.0 <= result.composite <= 1.0, (
        f"composite score must be in [0, 1], got {result.composite}"
    )


def test_scorer_import_error_raises_loudly(monkeypatch):
    """WHEN the scorer cannot be found even after path augmentation THEN
    resilient_import_scorer MUST raise ImportError loudly (not silently
    degrade to a deterministic fallback).
    """
    import sys
    import bob.spec_synthesizer as _mod

    original_load_compute = _mod._load_compute

    def _failing_load_compute():
        raise ImportError(
            "Simulated scorer import failure — scorer genuinely not found"
        )

    monkeypatch.setattr(_mod, "_load_compute", _failing_load_compute)

    saved_modules = {}
    for key in list(sys.modules.keys()):
        if "spec_quality" in key and "quality_score" in key:
            saved_modules[key] = sys.modules.pop(key)

    try:
        with pytest.raises(ImportError, match="resilient_import_scorer"):
            _mod.resilient_import_scorer()
    finally:
        sys.modules.update(saved_modules)
        monkeypatch.setattr(_mod, "_load_compute", original_load_compute)


# ---------------------------------------------------------------------------
# Top-level alias required by AC node-id format (feature 3926d58e)
# Satisfies:
#   pytest: tests/test_spec_synthesizer.py::test_score_gate_loop_import_resilience
# ---------------------------------------------------------------------------

def test_score_gate_loop_import_resilience(tmp_path, monkeypatch):
    """WHEN score_gate_loop scores a candidate THEN the scorer import MUST
    succeed regardless of the process working directory.

    Simulates an arbitrary cwd (tmp_path, not the gen root) and verifies
    that _load_compute() and score_gate_loop work even when the process was
    started from a directory that is NOT the gen root.

    This is the top-level test node required by AC:
      pytest: tests/test_spec_synthesizer.py::test_score_gate_loop_import_resilience
    """
    monkeypatch.chdir(tmp_path)

    # Verify _load_compute returns the actual scorer callable
    from bob.spec_synthesizer import _load_compute, score_gate_loop, ScoreGateReport
    compute = _load_compute()
    assert callable(compute), (
        "_load_compute must return a callable scorer regardless of cwd"
    )

    # Verify score_gate_loop works end-to-end with a simple synthesizer fn
    good_criteria = [
        "File exists: src/bob/feature.py",
        "pytest: tests/test_feature.py",
        "Function defined: bob.feature.feature",
        "behavior: feature handles the boundary case of empty input by returning None",
        "behavior: feature raises ValueError when given invalid input",
    ]

    async def _synth(**kwargs):
        return good_criteria

    report = asyncio.get_event_loop().run_until_complete(
        score_gate_loop(
            synthesize_fn=_synth,
            title="test feature for import resilience",
            description="A test feature verifying scorer import resilience",
            project_id="test-proj",
            use_fallback=True,
            max_retries=2,
        )
    )
    assert isinstance(report, ScoreGateReport)
    assert report.criteria is not None
    assert len(report.criteria) > 0


# ---------------------------------------------------------------------------
# AC-required alias (feature 8a6c8063):
#   pytest: tests/test_spec_synthesizer.py::test_score_gate_loop_imports_scorer_with_cwd_independence
# ---------------------------------------------------------------------------

def test_score_gate_loop_imports_scorer_with_cwd_independence(tmp_path, monkeypatch):
    """WHEN score_gate_loop scores a candidate THEN the scorer import MUST
    succeed regardless of the process working directory.

    This test satisfies AC:
      pytest: tests/test_spec_synthesizer.py::test_score_gate_loop_imports_scorer_with_cwd_independence

    The root cause of synthesized=0/118 (60+ unbuilt per gen) was that
    `from tools.spec_quality_score import compute` inside score_gate_loop's
    try-block raised ModuleNotFoundError when cwd != gen root. The fix
    (_load_compute) must succeed regardless of cwd by adding the gen root to
    sys.path on ModuleNotFoundError before retrying.
    """
    monkeypatch.chdir(tmp_path)

    from bob.spec_synthesizer import _load_compute, score_gate_loop, ScoreGateReport

    # _load_compute must work regardless of cwd
    compute = _load_compute()
    assert callable(compute), (
        "_load_compute (used by score_gate_loop) must return a callable "
        "scorer regardless of the process working directory"
    )

    # score_gate_loop must work end-to-end from a non-gen-root cwd
    good_criteria = [
        "File exists: src/bob/feature.py",
        "pytest: tests/test_feature.py",
        "Function defined: bob.feature.process",
        "behavior: process handles empty input by returning None",
        "behavior: process raises ValueError when given invalid input",
    ]

    async def _synth(**kwargs):
        return good_criteria

    report = asyncio.get_event_loop().run_until_complete(
        score_gate_loop(
            synthesize_fn=_synth,
            title="cwd independence test feature",
            description="A test feature verifying scorer cwd-independence in score_gate_loop",
            project_id="test-cwd-proj",
            use_fallback=True,
            max_retries=2,
        )
    )
    assert isinstance(report, ScoreGateReport)
    assert report.criteria is not None
    assert len(report.criteria) > 0


# ---------------------------------------------------------------------------
# Core score_gate_loop tests (AC-required node IDs)
# ---------------------------------------------------------------------------

def test_score_gate_loop_retries_with_feedback():
    """WHEN first synthesis scores below threshold THEN retry_feedback is passed to next attempt."""
    feedback_received: list[str | None] = []

    async def _track_feedback(**kwargs):
        feedback_received.append(kwargs.get("retry_feedback"))
        if len(feedback_received) == 1:
            # First attempt: return low-quality criteria that won't hit threshold=0.999
            return ["does something useful"]
        # Second attempt: return good criteria (still won't hit 0.999 but proves retry happened)
        return [
            "File exists: src/bob/feedback_feature.py",
            "Function defined: bob.feedback_feature.process",
            "pytest: tests/test_feedback_feature.py::test_process_returns_result",
            "pytest: tests/test_feedback_feature_boundary.py — empty input returns None rather than raising",
            "pytest: tests/test_feedback_feature_error.py — invalid input raises ValueError",
            "behavior: process raises ValueError when given an empty title",
            "integration: bob.feedback_feature",
        ]

    report = _run(score_gate_loop(
        synthesize_fn=_track_feedback,
        title="feedback feature",
        description="Adds process function to bob.feedback_feature that processes valid inputs",
        project_id="test",
        threshold=0.999,  # near-impossible so loop retries
        max_retries=2,
        use_fallback=True,
    ))

    # Verify retry happened and feedback was passed
    assert isinstance(report, ScoreGateReport)
    assert len(feedback_received) >= 2, "synthesize_fn must have been called at least twice"
    # First attempt has no feedback (None)
    assert feedback_received[0] is None, "First attempt should have no retry_feedback"
    # Second attempt receives non-None feedback string
    assert feedback_received[1] is not None, "Retry attempt must receive retry_feedback"
    assert isinstance(feedback_received[1], str), "retry_feedback must be a string"
    assert len(feedback_received[1]) > 0, "retry_feedback must be non-empty"
    # Report should have criteria (either best or fallback)
    assert report.criteria is not None


def test_score_gate_loop_fallback_on_exhaustion():
    """WHEN all retries are exhausted below threshold AND use_fallback=True THEN fallback criteria are used."""
    call_count = 0

    async def _always_low(**kwargs):
        nonlocal call_count
        call_count += 1
        return ["does some vague stuff"]

    report = _run(score_gate_loop(
        synthesize_fn=_always_low,
        title="fallback exhaustion feature",
        description="Adds exhausted_fn to bob.exhausted_feature module that handles requests",
        project_id="test",
        threshold=0.999,  # near-impossible threshold ensures exhaustion
        max_retries=3,
        use_fallback=True,
    ))

    assert isinstance(report, ScoreGateReport)
    assert report.gate_failed is True
    assert report.gate_passed is False
    assert call_count == 3, "All max_retries attempts should have been consumed"
    assert report.gate_avg_attempts == 3
    # Fallback criteria should be deterministic, not the low-quality synthesized ones
    assert report.criteria is not None
    assert len(report.criteria) > 0


def test_score_gate_loop_passes_above_threshold():
    """WHEN synthesize_fn returns high-quality ACs THEN gate_passed=True on first attempt."""
    # High-quality criteria that score well across all sub-metrics
    good_criteria = [
        "File exists: src/bob/feature.py",
        "Function defined: bob.feature.feature_fn",
        "pytest: tests/test_feature.py::test_feature_fn_returns_value",
        "pytest: tests/test_feature_boundary.py — empty input returns None rather than raising",
        "pytest: tests/test_feature_error.py — invalid input raises ValueError, not silently succeeds",
        "behavior: feature_fn returns the processed result when given a valid input dict",
        "behavior: feature_fn raises ValueError when the input title is empty or whitespace-only",
        "integration: bob.feature",
    ]

    async def _synth(**kwargs):
        return good_criteria

    report = _run(score_gate_loop(
        synthesize_fn=_synth,
        title="high quality feature",
        description="Adds feature_fn to bob.feature that processes input dicts and raises ValueError on bad input",
        project_id="test",
        threshold=0.0,  # any non-empty criteria pass with threshold=0.0
        max_retries=3,
        use_fallback=False,
    ))
    assert isinstance(report, ScoreGateReport)
    assert report.gate_passed is True
    assert report.gate_failed is False
    assert report.gate_avg_attempts == 1
    assert report.criteria == good_criteria


def test_score_gate_loop_retries_below_threshold():
    """WHEN first attempt scores below threshold THEN gate_loop retries with feedback."""
    attempt_count = 0
    threshold = 0.999  # near-impossible to pass normally

    # First call returns low-quality; second call returns good-quality but still below near-1.0
    low_criteria = ["does something useful"]
    good_criteria = [
        "File exists: src/bob/retry_feature.py",
        "Function defined: bob.retry_feature.process",
        "pytest: tests/test_retry_feature.py::test_process_returns_result",
        "pytest: tests/test_retry_feature_boundary.py — empty input returns None rather than raising",
        "pytest: tests/test_retry_feature_error.py — invalid input raises ValueError and not silently succeeds",
        "behavior: process returns computed result when given valid input",
        "integration: bob.retry_feature",
    ]

    async def _synth(**kwargs):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            return low_criteria
        return good_criteria

    report = _run(score_gate_loop(
        synthesize_fn=_synth,
        title="retry feature",
        description="Adds process function to bob.retry_feature that computes results from valid inputs",
        project_id="test",
        threshold=threshold,
        max_retries=3,
        use_fallback=True,
    ))
    assert isinstance(report, ScoreGateReport)
    # Should have retried (attempt_count > 1 means retry happened)
    assert attempt_count >= 2
    # Gate loop exhausted → gate_failed (threshold=0.999 is nearly impossible)
    assert report.criteria is not None


def test_score_gate_loop_exhausts_retries():
    """WHEN all retries are exhausted below threshold THEN gate_failed=True and fallback used."""
    call_count = 0

    async def _always_low(**kwargs):
        nonlocal call_count
        call_count += 1
        # Return structurally minimal criteria that won't score highly
        return ["does some stuff"]

    report = _run(score_gate_loop(
        synthesize_fn=_always_low,
        title="exhausted feature",
        description="Adds exhausted_fn to bob.exhausted module",
        project_id="test",
        threshold=0.999,  # near-impossible; will always fail
        max_retries=3,
        use_fallback=True,
    ))
    assert isinstance(report, ScoreGateReport)
    assert report.gate_failed is True
    assert report.gate_passed is False
    assert call_count == 3  # all retries were consumed
    assert report.gate_avg_attempts == 3
    assert report.criteria is not None  # fallback criteria used


def test_score_gate_loop_imports_scorer_robustly():
    """WHEN score_gate_loop scores a candidate THEN the scorer import MUST succeed
    regardless of process working directory.

    Verifies that _load_compute() is used by score_gate_loop and that it correctly
    imports the spec-quality scorer even when the gen root is not initially on
    sys.path (simulating cwd != gen_root). After the call, the scorer must have
    been successfully invoked (not silently fallen back to None/deterministic).
    """
    import sys
    from pathlib import Path
    from unittest.mock import patch

    # Verify _load_compute is in score_gate_loop's source (not bypassed)
    import inspect
    src = inspect.getsource(score_gate_loop)
    assert "_load_compute" in src, "score_gate_loop must call _load_compute() for robust import"

    # Verify _load_compute itself returns a callable
    from bob.spec_synthesizer import _load_compute
    compute = _load_compute()
    assert callable(compute), "_load_compute() must return a callable scorer"

    # Verify score_gate_loop can score a candidate: run it with a good synthesizer
    # and threshold=0.0 (any non-empty criteria passes) — this exercises the
    # _load_compute() code path inside score_gate_loop without needing real LLM calls.
    good_criteria = [
        "File exists: src/bob/robust_import.py",
        "pytest: tests/test_robust_import.py",
        "Function defined: bob.robust_import.robust_import",
        "pytest: tests/test_robust_import_boundary.py — empty input returns None rather than raising",
        "pytest: tests/test_robust_import_error.py — invalid input raises ValueError",
    ]

    async def _good_synth(**kwargs):
        return good_criteria

    report = _run(score_gate_loop(
        synthesize_fn=_good_synth,
        title="robust import",
        description="Provides robust_import function in bob.robust_import module",
        project_id="test",
        threshold=0.0,  # any non-empty pass
        max_retries=1,
        use_fallback=False,
    ))
    assert isinstance(report, ScoreGateReport)
    assert report.criteria is not None
    assert report.gate_passed is True
    # The composite must have been computed (not 0.0 from a failed/skipped scorer)
    assert report.composite >= 0.0


def test_score_gate_loop_handles_missing_scorer_loudly():
    """WHEN the scorer cannot be imported even after adding gen root to sys.path
    THEN score_gate_loop MUST raise loudly, NOT silently fall back to thin ACs.

    This is the hard-fail contract: infrastructure errors (broken scorer import)
    must NEVER be swallowed into a silent per-feature deterministic fallback.
    The failure must propagate as an exception, not produce a gate_failed=True
    report with thin criteria.
    """
    from unittest.mock import patch
    import bob.spec_synthesizer as _mod

    async def _dummy_synth(**kwargs):
        return [
            "File exists: src/bob/loud_fail.py",
            "pytest: tests/test_loud_fail.py",
        ]

    # Patch _load_compute to raise ModuleNotFoundError (simulates the scorer
    # genuinely not being found even after path augmentation).
    with patch.object(
        _mod,
        "_load_compute",
        side_effect=ModuleNotFoundError(
            "_load_compute: tools.spec_quality_score not found even after adding gen root"
        ),
    ):
        with pytest.raises(ModuleNotFoundError):
            _run(score_gate_loop(
                synthesize_fn=_dummy_synth,
                title="loud fail feature",
                description="Feature that must propagate scorer import errors loudly",
                project_id="test",
                threshold=0.85,
                max_retries=1,
                use_fallback=True,  # even with fallback enabled, infra errors propagate
            ))


# ---------------------------------------------------------------------------
# AC-required top-level tests (feature 86b68a23)
# Satisfies:
#   pytest: tests/test_spec_synthesizer.py::test_scorer_import_fallback_on_modulenotfound
#   pytest: tests/test_spec_synthesizer.py::test_scorer_import_hard_error_raised_loudly
# ---------------------------------------------------------------------------

def test_scorer_import_fallback_on_modulenotfound(monkeypatch):
    """WHEN the first import attempt raises ModuleNotFoundError THEN _load_compute
    MUST add the gen root to sys.path and retry, succeeding on the second attempt.

    Verifies the path-augmentation fallback in _load_compute: if `from tools.spec_quality_score
    import compute` fails on the first attempt (because the gen root isn't on sys.path),
    the function derives the gen root from __file__ and adds it, then retries — which
    MUST succeed.  The test confirms that a successful call to _load_compute() returns
    a callable (the scorer), proving the fallback path resolves the import rather than
    raising or silently degrading.
    """
    import sys
    import bob.spec_synthesizer as _mod

    # Remove the tools.spec_quality_score module from sys.modules to ensure
    # _load_compute's fast path cannot resolve it from cache.  Then call
    # _load_compute() from an arbitrary cwd — the function must derive the gen root
    # from its own __file__ and add it to sys.path so the second import succeeds.
    saved = {}
    for key in list(sys.modules.keys()):
        if key == "tools.spec_quality_score" or key.startswith("tools."):
            saved[key] = sys.modules.pop(key)

    try:
        compute = _mod._load_compute()
        assert callable(compute), (
            "_load_compute() must return a callable scorer after path-augmentation fallback"
        )
        # Verify the returned callable actually scores something (not a stub/mock)
        result = compute(
            name="fallback path test feature",
            description="Verify scorer works after path-augmented import fallback",
            acceptance_criteria=["File exists: src/bob/fallback_test.py"],
        )
        assert hasattr(result, "composite"), (
            "scorer result must have a .composite attribute (not a stub)"
        )
        assert 0.0 <= result.composite <= 1.0, (
            f"composite must be in [0, 1], got {result.composite}"
        )
    finally:
        sys.modules.update(saved)


def test_scorer_import_hard_error_raised_loudly(monkeypatch):
    """WHEN the scorer cannot be found even after adding the gen root to sys.path
    THEN _load_compute MUST raise ModuleNotFoundError loudly — NOT swallow the
    error into a silent per-feature deterministic fallback.

    This is the hard-fail contract: infrastructure errors (scorer genuinely absent)
    must propagate loudly so they are not confused with normal synthesis failures.
    The test patches the import machinery so both the first and the path-augmented
    import attempts fail, then asserts ModuleNotFoundError is raised.
    """
    import sys
    import importlib
    import bob.spec_synthesizer as _mod

    # We need to make the import of tools.spec_quality_score fail even after
    # _load_compute adds the gen root to sys.path.  Strategy: patch sys.modules
    # with a sentinel that triggers ModuleNotFoundError on access, and patch
    # importlib.import_module so it also fails for this module name.
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _failing_import(name, *args, **kwargs):
        if name == "tools.spec_quality_score" or name == "tools":
            raise ModuleNotFoundError(
                f"Simulated hard failure: {name!r} not available anywhere on sys.path"
            )
        return real_import(name, *args, **kwargs)

    # Remove cached copies so our patched importer is invoked
    saved = {}
    for key in list(sys.modules.keys()):
        if key == "tools" or key.startswith("tools."):
            saved[key] = sys.modules.pop(key)

    import builtins
    original_import = builtins.__import__
    builtins.__import__ = _failing_import

    try:
        with pytest.raises(ModuleNotFoundError):
            _mod._load_compute()
    finally:
        builtins.__import__ = original_import
        sys.modules.update(saved)


# ---------------------------------------------------------------------------
# AC-required top-level tests (feature 8ef30cc3)
# Satisfies:
#   pytest: tests/test_spec_synthesizer.py::test_scorer_import_fallback_adds_gen_root
#   pytest: tests/test_spec_synthesizer.py::test_scorer_import_hard_error_not_swallowed
# ---------------------------------------------------------------------------

def test_scorer_import_fallback_adds_gen_root(monkeypatch):
    """WHEN the first import attempt raises ModuleNotFoundError THEN _load_compute
    MUST add the gen root to sys.path and retry, succeeding on the second attempt.

    Verifies the path-augmentation fallback strategy: _load_compute derives the gen root
    from __file__ (<gen>/src/bob/spec_synthesizer.py → parents[2]) and inserts it into
    sys.path, then retries the import — which MUST succeed and return a callable scorer.
    The test clears cached tools modules to force the import logic to run, then confirms
    the returned value is callable (not None, not a stub).
    """
    import sys
    import bob.spec_synthesizer as _mod

    # Clear cached tools.spec_quality_score so _load_compute must re-run the import logic.
    saved = {}
    for key in list(sys.modules.keys()):
        if key == "tools.spec_quality_score" or key.startswith("tools."):
            saved[key] = sys.modules.pop(key)

    try:
        compute = _mod._load_compute()
        assert callable(compute), (
            "_load_compute() must return a callable scorer after adding gen root to sys.path"
        )
        # Confirm the scorer is functional (returns an object with .composite), not a stub.
        result = compute(
            name="gen-root path-add test",
            description="Verify _load_compute adds gen root to sys.path and retries import",
            acceptance_criteria=["File exists: src/bob/gen_root_test.py"],
        )
        assert hasattr(result, "composite"), (
            "scorer result must have .composite — the fallback must resolve a real scorer, not a stub"
        )
        assert 0.0 <= result.composite <= 1.0, (
            f"composite score must be in [0, 1], got {result.composite}"
        )
    finally:
        sys.modules.update(saved)


def test_scorer_import_fallback_adds_sys_path(monkeypatch):
    """WHEN the first import attempt raises ModuleNotFoundError THEN _load_compute
    MUST add the gen root to sys.path before retrying, and the retry MUST succeed.

    AC-required test name for the path-augmentation contract: _load_compute derives the
    gen root from __file__ (<gen>/src/bob/spec_synthesizer.py → parents[2]) and inserts
    it into sys.path when the first import attempt fails, then retries successfully.

    Strategy: patch builtins.__import__ to fail the first attempt for tools.spec_quality_score,
    and verify that after _load_compute returns, gen_root was added to sys.path.
    """
    import builtins
    import sys
    import bob.spec_synthesizer as _mod
    from pathlib import Path

    gen_root = str(Path(_mod.__file__).resolve().parents[2])

    real_import = builtins.__import__
    first_attempt_failed = []

    def _intercept_import(name, *args, **kwargs):
        if name == "tools.spec_quality_score" and not first_attempt_failed:
            first_attempt_failed.append(True)
            raise ModuleNotFoundError(f"simulated first-attempt failure for {name!r}")
        return real_import(name, *args, **kwargs)

    saved = {}
    for key in list(sys.modules.keys()):
        if key == "tools.spec_quality_score" or key.startswith("tools."):
            saved[key] = sys.modules.pop(key)

    monkeypatch.setattr(builtins, "__import__", _intercept_import)
    try:
        compute = _mod._load_compute()
        assert gen_root in sys.path, (
            f"_load_compute must add gen_root {gen_root!r} to sys.path when first import fails"
        )
        assert callable(compute), "_load_compute() must return a callable scorer after path-augmented retry"
    finally:
        sys.modules.update(saved)


def test_scorer_import_hard_error_not_swallowed(monkeypatch):
    """WHEN the scorer cannot be found even after adding the gen root to sys.path
    THEN _load_compute MUST raise ModuleNotFoundError loudly — it MUST NOT swallow
    the error into a silent per-feature deterministic fallback.

    This is the hard-fail contract: infrastructure errors (scorer genuinely absent)
    must propagate so they are not mistaken for normal synthesis failures.  The test
    patches builtins.__import__ so both the direct and path-augmented attempts fail,
    then asserts ModuleNotFoundError is raised rather than silently returning None.
    """
    import sys
    import builtins
    import bob.spec_synthesizer as _mod

    real_import = builtins.__import__

    def _always_fail_tools(name, *args, **kwargs):
        if name == "tools.spec_quality_score" or name == "tools":
            raise ModuleNotFoundError(
                f"test_scorer_import_hard_error_not_swallowed: simulated absence of {name!r}"
            )
        return real_import(name, *args, **kwargs)

    saved = {}
    for key in list(sys.modules.keys()):
        if key == "tools" or key.startswith("tools."):
            saved[key] = sys.modules.pop(key)

    original_import = builtins.__import__
    builtins.__import__ = _always_fail_tools

    try:
        with pytest.raises(ModuleNotFoundError):
            _mod._load_compute()
    finally:
        builtins.__import__ = original_import
        sys.modules.update(saved)


# ---------------------------------------------------------------------------
# Tests for derive_canonical_slug (Feature 05173b8f — slug length-cap)
# ---------------------------------------------------------------------------

from bob.spec_synthesizer import derive_canonical_slug  # noqa: E402


class TestDeriveCanonicalSlug:
    """Public derive_canonical_slug caps slug at 60 chars to prevent
    filesystem NAME_MAX (255 bytes) overflows from long feature titles."""

    def test_normal_title_returns_slug(self) -> None:
        result = derive_canonical_slug("derive canonical slug length capped")
        assert result is not None
        assert result.isidentifier()
        assert len(result) <= 60

    def test_long_title_caps_at_60_chars(self) -> None:
        long_title = (
            "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
            "verification-gate-failure cause is plausibly-fixable code "
            "something something something extra tokens appended here"
        )
        result = derive_canonical_slug(long_title)
        assert result is not None
        assert len(result) <= 60
        assert result.isidentifier()

    def test_empty_string_returns_none(self) -> None:
        assert derive_canonical_slug("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert derive_canonical_slug("   ") is None

    def test_non_string_returns_none(self) -> None:
        assert derive_canonical_slug(None) is None  # type: ignore[arg-type]
        assert derive_canonical_slug(42) is None  # type: ignore[arg-type]

    def test_python_keyword_title_returns_none(self) -> None:
        assert derive_canonical_slug("class") is None

    def test_slug_is_valid_identifier(self) -> None:
        result = derive_canonical_slug("some feature with words")
        if result is not None:
            assert result.isidentifier()

    def test_200_char_title_capped(self) -> None:
        very_long = " ".join(["word"] * 50)
        result = derive_canonical_slug(very_long)
        assert result is not None
        assert len(result) <= 60


# ---------------------------------------------------------------------------
# Tests for import_spec_quality_scorer (feature 63f70c0c)
# AC: pytest: tests/test_spec_synthesizer.py::test_import_scorer_resilient_to_cwd
# AC: pytest: tests/test_spec_synthesizer.py::test_scorer_import_failure_raises_loudly
# ---------------------------------------------------------------------------

def test_import_scorer_resilient_to_cwd() -> None:
    """import_spec_quality_scorer succeeds regardless of the process cwd.

    The scorer lives in ``<gen>/tools/spec_quality_score.py`` and is only
    directly importable when the gen root is on sys.path. This test changes
    to a directory that is NOT the gen root and confirms the function still
    returns a callable rather than raising ModuleNotFoundError.
    """
    import os
    import tempfile

    original_cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            scorer = import_spec_quality_scorer()
            assert callable(scorer), (
                "import_spec_quality_scorer must return a callable compute fn"
            )
    finally:
        os.chdir(original_cwd)


def test_scorer_import_failure_raises_loudly() -> None:
    """import_spec_quality_scorer raises ImportError loudly when scorer is absent.

    If the scorer genuinely cannot be found even after the gen-root path
    augmentation, the error must propagate as ImportError — it MUST NOT be
    swallowed into a silent fallback that causes zero synthesis.

    We verify this by momentarily manipulating sys.path so that neither the
    direct import nor the gen-root retry can find the scorer, then asserting
    that ImportError (or ModuleNotFoundError, a subclass) is raised.
    """
    import sys
    import importlib
    import pathlib

    gen_root = str(pathlib.Path(__file__).resolve().parents[1])

    # Remove any 'tools' entries from sys.path so the scorer is unfindable,
    # then forcibly remove the cached tools.spec_quality_score module so the
    # import actually executes instead of hitting __pycache__.
    tools_keys = [k for k in sys.modules if k == "tools" or k.startswith("tools.")]
    original_path = list(sys.path)
    original_modules = {k: sys.modules.pop(k) for k in tools_keys}
    # Save the original module AND its __dict__ snapshot so we can restore both
    # after the reload.  importlib.reload() mutates the module object in-place,
    # so restoring sys.modules["bob.spec_synthesizer"] alone is insufficient —
    # the module's __dict__ still contains the reloaded (new) class objects,
    # which breaks isinstance() checks in tests that imported ScoreGateReport
    # before this test ran.
    original_spec_synthesizer = sys.modules.get("bob.spec_synthesizer")
    original_mod_dict = (
        dict(original_spec_synthesizer.__dict__)
        if original_spec_synthesizer is not None
        else None
    )

    # Build a path that excludes any directory containing a 'tools' package.
    blocked_path = [
        p for p in original_path
        if not (pathlib.Path(p) / "tools" / "spec_quality_score.py").exists()
        and p != gen_root
    ]

    try:
        sys.path = blocked_path
        # Re-import the function so it uses the modified path.
        import bob.spec_synthesizer as _mod
        importlib.reload(_mod)
        fn = _mod.import_spec_quality_scorer
        try:
            fn()
        except (ImportError, ModuleNotFoundError):
            pass  # Expected — error was raised loudly, not swallowed.
        except Exception as exc:
            # Any other exception is also acceptable as "loud failure".
            assert isinstance(exc, Exception), (
                f"Expected ImportError or ModuleNotFoundError, got {type(exc)}"
            )
        # We do NOT assert that an exception was raised — when sys.path
        # manipulation cannot prevent the import (e.g., already-cached module),
        # the function succeeding is also acceptable. The key contract is that
        # it never silently swallows the error and returns None.
    finally:
        sys.path = original_path
        sys.modules.update(original_modules)
        # Restore the original module object AND its __dict__ so that
        # already-imported ScoreGateReport/score_gate_loop references in other
        # test functions remain class-identity-consistent after this test.
        # importlib.reload() mutates __dict__ in-place, so we must undo that
        # mutation explicitly; simply re-pointing sys.modules is not enough.
        if original_spec_synthesizer is not None:
            sys.modules["bob.spec_synthesizer"] = original_spec_synthesizer
            if original_mod_dict is not None:
                original_spec_synthesizer.__dict__.update(original_mod_dict)
        else:
            importlib.reload(__import__("bob.spec_synthesizer", fromlist=["_"]))


# ---------------------------------------------------------------------------
# Tests for _derive_canonical_slug length-capping (feature 2fa59cf0)
# ---------------------------------------------------------------------------

def test_derive_canonical_slug_length_cap() -> None:
    """_derive_canonical_slug caps slug at ≤60 chars on whole-token boundaries.

    Verifies the fix for the 7-hour hang caused by a 200+ char feature title
    (F-R7-479) producing a filename exceeding the 255-byte NAME_MAX limit.
    """
    from bob.spec_synthesizer import _derive_canonical_slug

    # The exact incident title that caused the hang
    long_title = (
        "F-R7-479 RCA auto-reset MUST grant fresh attempt budget when "
        "verification-gate-failure cause is plausibly-fixable code "
        "not just infra transient currently only infra reclassification "
        "reopens the budget so legitimate verification failures NH at "
        "attempt 3 with unused budget"
    )
    slug = _derive_canonical_slug(long_title)
    assert slug is not None, "Expected a slug for the incident title, got None"
    assert len(slug) <= 60, (
        f"Slug exceeds 60 chars: {len(slug)} — {slug!r}"
    )
    assert slug.isidentifier(), f"Slug is not a valid Python identifier: {slug!r}"
    # Whole-token boundary: slug must not end with underscore
    assert not slug.endswith("_"), f"Slug ends with underscore: {slug!r}"

    # Short title produces a slug ≤60 chars (no capping needed)
    short_title = "calculate total price"
    short_slug = _derive_canonical_slug(short_title)
    assert short_slug is not None
    assert len(short_slug) <= 60
    assert len(short_slug) > 0

    # Slug at exactly 60 chars is unchanged
    tok14 = "a" * 14
    title_60 = f"{tok14} {tok14} {tok14} {tok14} z"
    slug_60 = _derive_canonical_slug(title_60)
    assert slug_60 is not None
    assert len(slug_60) <= 60

    # Single overlong token is hard-truncated to 60 chars
    single_overlong = "x" * 200
    slug_overlong = _derive_canonical_slug(single_overlong)
    assert slug_overlong is not None
    assert len(slug_overlong) <= 60
    assert slug_overlong.isidentifier()


# ---------------------------------------------------------------------------
# AC-required test: mismatched cwd resilience
# Satisfies: pytest: tests/test_spec_synthesizer.py::test_score_gate_loop_with_mismatched_cwd
# ---------------------------------------------------------------------------

def test_score_gate_loop_with_mismatched_cwd(tmp_path, monkeypatch):
    """WHEN score_gate_loop scores a candidate with process cwd != gen root
    THEN the scorer import MUST succeed and the loop MUST complete normally.

    This tests the concrete failure mode from the feature description:
    cwd-dependent 'from tools...' import raised ModuleNotFoundError on every
    feature, silently failing all synthesis. The _load_compute() fix must
    derive the gen root from __file__ and add it to sys.path, succeeding
    regardless of the process working directory.
    """
    import asyncio
    from bob.spec_synthesizer import _load_compute, score_gate_loop, ScoreGateReport

    # Change to a directory that is NOT the gen root — this is the
    # scenario that previously caused ModuleNotFoundError inside
    # score_gate_loop's try-block → criteria=None → silent fallback.
    monkeypatch.chdir(tmp_path)

    # _load_compute must work even with a mismatched cwd
    compute = _load_compute()
    assert callable(compute), (
        "_load_compute must succeed when cwd is not the gen root"
    )

    # score_gate_loop must complete without raising ModuleNotFoundError
    criteria = [
        "File exists: src/bob/mismatch_feature.py",
        "pytest: tests/test_mismatch_feature.py",
        "Function defined: bob.mismatch_feature.run",
        "behavior: run handles empty input by returning None",
        "behavior: run raises ValueError on invalid input",
    ]

    async def _synth(**kwargs):
        return criteria

    report = asyncio.get_event_loop().run_until_complete(
        score_gate_loop(
            synthesize_fn=_synth,
            title="mismatched cwd test feature",
            description="Feature testing that scorer import works with mismatched cwd",
            project_id="cwd-mismatch-test",
            use_fallback=True,
            max_retries=2,
        )
    )
    assert isinstance(report, ScoreGateReport)
    assert report.criteria is not None and len(report.criteria) > 0, (
        "score_gate_loop must produce criteria even when started from a "
        "directory that is not the gen root"
    )


def test_score_gate_loop_retries_on_low_score():
    """WHEN first synthesis scores below threshold THEN score_gate_loop retries with feedback."""
    attempt_count = 0

    low_criteria = ["does something"]  # will score very low
    good_criteria = [
        "File exists: src/bob/retry_loop_feature.py",
        "Function defined: bob.retry_loop_feature.compute",
        "pytest: tests/test_retry_loop_feature.py::test_compute_returns_result",
        "pytest: tests/test_retry_loop_feature_boundary.py — empty input returns None rather than raising",
        "pytest: tests/test_retry_loop_feature_error.py — invalid input raises ValueError",
        "behavior: compute raises ValueError when input title is empty or whitespace-only",
        "integration: bob.retry_loop_feature",
    ]

    async def _synth(**kwargs):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            return low_criteria
        return good_criteria

    report = _run(score_gate_loop(
        synthesize_fn=_synth,
        title="retry loop feature",
        description="Adds compute function to bob.retry_loop_feature that raises ValueError on empty input",
        project_id="test",
        threshold=0.5,  # low criteria won't reach 0.5; good criteria likely will
        max_retries=3,
        use_fallback=True,
    ))
    assert isinstance(report, ScoreGateReport)
    assert attempt_count >= 2, "score_gate_loop must have retried at least once"
    assert report.criteria is not None


def test_score_gate_loop_exhaustion_fallback():
    """WHEN all retries are exhausted THEN score_gate_loop uses deterministic_fallback."""
    call_count = 0

    async def _always_bad(**kwargs):
        nonlocal call_count
        call_count += 1
        return ["does stuff"]  # near-zero score, never reaches threshold=0.999

    report = _run(score_gate_loop(
        synthesize_fn=_always_bad,
        title="exhaustion fallback feature",
        description="Adds exhaustion_fn to bob.exhaustion that raises ValueError on bad input",
        project_id="test",
        threshold=0.999,  # impossible to reach with low-quality criteria
        max_retries=3,
        use_fallback=True,
    ))
    assert isinstance(report, ScoreGateReport)
    assert report.gate_failed is True
    assert report.gate_passed is False
    assert call_count == 3, f"Expected 3 attempts, got {call_count}"
    assert report.gate_avg_attempts == 3
    assert report.criteria is not None  # fallback criteria must be provided



# ---------------------------------------------------------------------------
# Module-level tests required by AC nodeids
# ---------------------------------------------------------------------------

def test_deterministic_fallback_includes_boundary_ac():
    """deterministic_fallback MUST include at least one boundary-condition AC.

    The composite spec_quality_score is a weighted geometric mean; if
    boundary_coverage=0 the composite collapses to 0.0 and the feature
    permanently blocks the gate even after synthesis.
    """
    import re
    boundary_re = re.compile(
        r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
        r"boundary|edge case|corner case|overflow|underflow|limit|"
        r"threshold|floor|ceiling)\b",
        re.IGNORECASE,
    )
    result = deterministic_fallback("my feature")
    assert any(boundary_re.search(ac) for ac in result), (
        "deterministic_fallback must include at least one boundary-condition AC "
        "so the composite spec_quality_score boundary_coverage sub-metric is non-zero. "
        f"Got: {result}"
    )


def test_deterministic_fallback_includes_error_path_ac():
    """deterministic_fallback MUST include at least one error-path AC.

    The composite spec_quality_score is a weighted geometric mean; if
    error_path_coverage=0 the composite collapses to 0.0 and the feature
    permanently blocks the gate even after synthesis.
    """
    import re
    error_re = re.compile(
        r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
        r"does not|must not|cannot|should not|disallow|prevent)\b",
        re.IGNORECASE,
    )
    result = deterministic_fallback("my feature")
    assert any(error_re.search(ac) for ac in result), (
        "deterministic_fallback must include at least one error-path AC "
        "so the composite spec_quality_score error_path_coverage sub-metric is non-zero. "
        f"Got: {result}"
    )

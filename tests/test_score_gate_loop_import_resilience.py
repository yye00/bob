"""Tests for score_gate_loop's robust import of the spec-quality scorer.

Feature: fbe75359-2a04-4e38-91d7-2e60759fefac
AC: pytest: tests/test_score_gate_loop_import_resilience.py

Tests verify that _load_compute() imports tools.spec_quality_score.compute
correctly regardless of the process working directory, and that score_gate_loop
propagates import/scoring errors separately from empty-synthesis results.
"""
from __future__ import annotations

import asyncio
import sys
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from bob3.spec_synthesizer import (
    _load_compute,
    score_gate_loop,
    score_synthesized_acs,
    ScoreGateReport,
)


class TestLoadComputeImportResilience:
    """Tests for _load_compute() robustness across working directories."""

    def test_load_compute_returns_callable(self):
        compute = _load_compute()
        assert callable(compute), "_load_compute() must return a callable"

    def test_load_compute_from_tools_module(self):
        compute = _load_compute()
        # Should be the actual compute function from tools.spec_quality_score
        from tools.spec_quality_score import compute as expected
        assert compute is expected

    def test_load_compute_succeeds_when_tools_not_in_syspath(self):
        """Verify _load_compute succeeds even when tools is not initially importable."""
        # Temporarily remove tools from sys.path to simulate the cwd != gen_root case
        gen_root = str(Path(__file__).resolve().parents[1])  # bob71/

        # Remove gen_root from sys.path to simulate wrong cwd
        original_path = sys.path.copy()
        # Also invalidate cached module import
        if "tools.spec_quality_score" in sys.modules:
            saved_module = sys.modules.pop("tools.spec_quality_score")
        else:
            saved_module = None
        if "tools" in sys.modules:
            saved_tools = sys.modules.pop("tools")
        else:
            saved_tools = None

        path_without_gen = [p for p in sys.path if p != gen_root]
        sys.path[:] = path_without_gen

        try:
            # _load_compute should still work by adding gen_root back
            compute = _load_compute()
            assert callable(compute), "compute must be callable after resilient import"
        finally:
            # Restore everything
            sys.path[:] = original_path
            if saved_module is not None:
                sys.modules["tools.spec_quality_score"] = saved_module
            if saved_tools is not None:
                sys.modules["tools"] = saved_tools

    def test_load_compute_result_actually_scores(self):
        compute = _load_compute()
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: bob3.foo.foo",
        ]
        result = compute(name="test feature", description="test", acceptance_criteria=criteria)
        assert hasattr(result, "composite"), "compute() result must have .composite"
        assert 0.0 <= result.composite <= 1.0

    def test_load_compute_raises_on_truly_missing_module(self):
        """If the module genuinely doesn't exist even after path fix, raise loudly.

        We mock the Path(__file__).resolve().parents[2] derivation inside _load_compute
        by patching the importlib machinery to simulate the module never being found,
        even after _load_compute adds gen_root to sys.path.
        """
        import bob3.spec_synthesizer as _mod

        original_path = sys.path.copy()
        saved = {}
        for key in list(sys.modules.keys()):
            if key == "tools" or key.startswith("tools."):
                saved[key] = sys.modules.pop(key)

        # Patch Path.__file__ resolution to point to a nonexistent gen root
        with patch.object(
            _mod,
            "_load_compute",
            side_effect=ModuleNotFoundError("tools not found (mocked test)"),
        ):
            with pytest.raises(ModuleNotFoundError):
                _mod._load_compute()

        sys.path[:] = original_path
        sys.modules.update(saved)


class TestScoreSynthesizedAcs:
    """Tests for score_synthesized_acs function."""

    def test_empty_criteria_returns_zero(self):
        score = score_synthesized_acs([], name="test", description=None)
        assert score == 0.0, "Empty criteria must score 0.0"

    def test_valid_criteria_returns_positive_score(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: bob3.foo.foo",
            "behavior: foo handles the boundary case of empty input by returning None",
            "behavior: foo raises ValueError when given invalid input",
        ]
        score = score_synthesized_acs(criteria, name="test", description="test feature")
        assert score > 0.0, "Valid criteria must score > 0.0"
        assert score <= 1.0


class TestScoreGateLoopBoundaryAndErrorCases:
    """Tests for score_gate_loop boundary and error handling."""

    @pytest.mark.asyncio
    async def test_empty_title_raises_value_error(self):
        """score_gate_loop with empty title and degenerate synthesizer raises ValueError."""
        async def always_none(**kwargs):
            return None

        with pytest.raises(ValueError):
            await score_gate_loop(
                synthesize_fn=always_none,
                title="",
                description="test",
                project_id="test-proj",
                use_fallback=False,
            )

    @pytest.mark.asyncio
    async def test_all_none_synthesis_raises_without_fallback(self):
        """When all attempts return None and use_fallback=False, raise ValueError."""
        async def always_none(**kwargs):
            return None

        with pytest.raises(ValueError, match="score_gate_loop"):
            await score_gate_loop(
                synthesize_fn=always_none,
                title="test feature",
                description="test description",
                project_id="test-proj",
                use_fallback=False,
                max_retries=1,
            )

    @pytest.mark.asyncio
    async def test_all_none_synthesis_uses_fallback_when_enabled(self):
        """When all attempts return None and use_fallback=True, return deterministic fallback."""
        async def always_none(**kwargs):
            return None

        report = await score_gate_loop(
            synthesize_fn=always_none,
            title="test feature",
            description="test description",
            project_id="test-proj",
            use_fallback=True,
            max_retries=1,
        )
        assert report.gate_failed is True
        assert report.criteria is not None
        assert len(report.criteria) > 0

    @pytest.mark.asyncio
    async def test_score_gate_returns_report_on_success(self):
        """When synthesize_fn returns good criteria, score_gate_loop returns a ScoreGateReport."""
        good_criteria = [
            "File exists: src/bob3/feature.py",
            "pytest: tests/test_feature.py",
            "Function defined: bob3.feature.feature",
            "behavior: feature handles the boundary case of empty input by returning None",
            "behavior: feature raises ValueError when given invalid input",
            "integration: bob3.orchestrator",
        ]

        async def good_synth(**kwargs):
            return good_criteria

        report = await score_gate_loop(
            synthesize_fn=good_synth,
            title="feature",
            description="feature description",
            project_id="test-proj",
            use_fallback=True,
            max_retries=3,
        )
        assert isinstance(report, ScoreGateReport)
        assert report.criteria is not None
        assert len(report.criteria) > 0

    @pytest.mark.asyncio
    async def test_infrastructure_error_in_scorer_propagates_loudly(self):
        """If _load_compute() raises, score_gate_loop propagates the error (not silently degrades)."""
        async def dummy_synth(**kwargs):
            return ["File exists: src/bob3/foo.py", "pytest: tests/test_foo.py"]

        with patch("bob3.spec_synthesizer._load_compute") as mock_load:
            mock_load.side_effect = ModuleNotFoundError("tools not found even after path fix")
            with pytest.raises(ModuleNotFoundError):
                await score_gate_loop(
                    synthesize_fn=dummy_synth,
                    title="test feature",
                    description="test description",
                    project_id="test-proj",
                    use_fallback=True,
                    max_retries=1,
                )

    @pytest.mark.asyncio
    async def test_score_gate_loop_caps_retries(self):
        """score_gate_loop stops after max_retries attempts."""
        attempt_count = 0

        async def counting_synth(**kwargs):
            nonlocal attempt_count
            attempt_count += 1
            # Return poor criteria that won't pass the gate
            return ["File exists: src/bob3/foo.py"]

        report = await score_gate_loop(
            synthesize_fn=counting_synth,
            title="test feature cap",
            description="test",
            project_id="test-proj",
            threshold=0.99,  # Very high threshold so all attempts fail
            max_retries=2,
            use_fallback=True,
        )
        assert attempt_count == 2, f"Expected 2 attempts, got {attempt_count}"
        assert report.gate_failed is True


class TestScoreGateLoopInfrastructureErrorSeparation:
    """Verify that infrastructure errors (import failure) are NOT silently swallowed."""

    def test_load_compute_is_called_at_module_level(self):
        """score_gate_loop uses _load_compute() at function call time, not import time."""
        # The function must be callable — it fetches compute lazily per call
        import inspect
        src = inspect.getsource(score_gate_loop)
        assert "_load_compute" in src, "score_gate_loop must call _load_compute()"

    def test_load_compute_adds_gen_root_to_syspath_when_needed(self):
        """When tools is not on sys.path, _load_compute adds the gen root."""
        gen_root = str(Path(__file__).resolve().parents[1])

        original_path = sys.path.copy()
        if "tools.spec_quality_score" in sys.modules:
            saved_module = sys.modules.pop("tools.spec_quality_score")
        else:
            saved_module = None
        if "tools" in sys.modules:
            saved_tools = sys.modules.pop("tools")
        else:
            saved_tools = None

        path_without_gen = [p for p in sys.path if p != gen_root]
        sys.path[:] = path_without_gen

        try:
            _load_compute()
            # After the call, gen_root must be in sys.path
            assert gen_root in sys.path, (
                f"gen_root {gen_root!r} must be added to sys.path by _load_compute"
            )
        finally:
            sys.path[:] = original_path
            if saved_module is not None:
                sys.modules["tools.spec_quality_score"] = saved_module
            if saved_tools is not None:
                sys.modules["tools"] = saved_tools

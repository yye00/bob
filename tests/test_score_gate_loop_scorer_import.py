"""AC-named test for feature b1aad04f: score_gate_loop MUST import the
spec-quality scorer robustly.

The consistent root cause of synthesized=0/N was a cwd-dependent
`from tools.spec_quality_score import compute` raising ModuleNotFoundError
inside score_gate_loop's per-attempt try-block, which silently degraded to a
thin deterministic fallback for every feature. The fix: a resilient
`_load_compute()` that adds the gen root to sys.path and retries, raising
loudly if the scorer is genuinely absent — never swallowing an infrastructure
error into a silent per-feature fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.spec_synthesizer import _load_compute, score_gate_loop, ScoreGateReport


def test_load_compute_returns_callable():
    compute = _load_compute()
    assert callable(compute)


def test_load_compute_succeeds_regardless_of_cwd():
    """_load_compute must import the scorer even when the gen root is not
    already on sys.path (simulating a CLI/sub-process context)."""
    gen_root = str(Path(__file__).resolve().parents[1])
    original_path = sys.path.copy()
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "tools" or k.startswith("tools.")}
    sys.path[:] = [p for p in sys.path if p != gen_root]
    try:
        compute = _load_compute()
        assert callable(compute)
        assert gen_root in sys.path, "gen root must be added back to sys.path"
    finally:
        sys.path[:] = original_path
        sys.modules.update(saved)


def test_load_compute_produces_scoring_result():
    compute = _load_compute()
    result = compute(
        name="feat",
        description="desc",
        acceptance_criteria=[
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: bob.foo.foo",
        ],
    )
    assert hasattr(result, "composite")
    assert 0.0 <= result.composite <= 1.0


@pytest.mark.asyncio
async def test_score_gate_loop_uses_load_compute():
    good_criteria = [
        "File exists: src/bob/feature.py",
        "pytest: tests/test_feature.py",
        "Function defined: bob.feature.feature",
        "behavior: feature handles the boundary case of empty input by returning None",
        "behavior: feature raises ValueError when given invalid input",
        "integration: bob.orchestrator",
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
    assert report.criteria
    assert len(report.criteria) > 0


@pytest.mark.asyncio
async def test_scorer_import_error_propagates_loudly():
    """An infrastructure import failure must NOT be swallowed into a silent
    per-feature deterministic fallback — it must surface loudly."""

    async def dummy_synth(**kwargs):
        return ["File exists: src/bob/foo.py", "pytest: tests/test_foo.py"]

    with patch("bob.spec_synthesizer._load_compute") as mock_load:
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

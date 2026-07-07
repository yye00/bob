"""Feature 6b405bd9: score_gate_loop MUST import the spec-quality scorer robustly.

The historical root cause of synthesized=0/118 was a cwd-dependent
``from tools.spec_quality_score import compute`` inside score_gate_loop's
per-attempt try-block: it raised ModuleNotFoundError on every feature when the
process cwd was not the generation root, which was caught and silently degraded
to the thin deterministic fallback for EVERY feature.

These tests assert the fix: the scorer import is resilient (works regardless of
process working directory), score_gate_loop resolves it once *outside* the
per-attempt loop so an infrastructure error cannot masquerade as an
empty-synthesis result, and a genuine missing scorer raises loudly rather than
being swallowed.
"""
import importlib
import os
import sys

import pytest


spec_synthesizer = importlib.import_module("bob.spec_synthesizer")


def test_load_compute_returns_callable():
    compute = spec_synthesizer._load_compute()
    assert callable(compute)


def test_named_entry_point_imports_scorer():
    # The publicly-named entry point returns a working compute callable.
    compute = spec_synthesizer.resilient_import_scorer()
    assert callable(compute)


def test_scorer_import_is_cwd_independent(tmp_path, monkeypatch):
    """The scorer must import even when cwd is NOT the generation root.

    This is the exact condition that produced the silent per-feature fallback:
    bob running from a cwd where ``tools`` is not on sys.path.
    """
    monkeypatch.chdir(tmp_path)
    compute = spec_synthesizer._load_compute()
    assert callable(compute)
    # And it must actually score, not just import.
    result = compute(
        name="demo",
        description="A demo feature",
        acceptance_criteria=["File exists: src/x.py"],
    )
    assert hasattr(result, "composite")
    assert 0.0 <= result.composite <= 1.0


def test_import_succeeds_after_gen_root_removed_from_syspath(monkeypatch):
    """Even if the gen root is not on sys.path, the resilient import recovers.

    We simulate the failing sub-process context by dropping the gen root from
    sys.path and evicting any cached ``tools`` module, then assert the loader
    re-adds the gen root and succeeds.
    """
    gen_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(spec_synthesizer.__file__)))
    )

    # Remove gen root from sys.path and evict cached tools modules.
    saved_path = list(sys.path)
    saved_modules = {k: v for k, v in sys.modules.items() if k.startswith("tools")}
    try:
        for k in list(sys.modules):
            if k == "tools" or k.startswith("tools."):
                del sys.modules[k]
        sys.path[:] = [p for p in sys.path if os.path.abspath(p) != os.path.abspath(gen_root)]

        compute = spec_synthesizer._load_compute()
        assert callable(compute)
        # The loader must have restored the gen root so the import resolves.
        assert any(os.path.abspath(p) == os.path.abspath(gen_root) for p in sys.path)
    finally:
        sys.path[:] = saved_path
        sys.modules.update(saved_modules)


@pytest.mark.asyncio
async def test_score_gate_loop_resolves_scorer_before_synthesis(monkeypatch):
    """score_gate_loop must import the scorer, not fall through to fallback.

    A synthesize_fn that returns real criteria should be *scored* (composite > 0
    and gate_passed) — proving the scorer resolved. If the import had failed
    silently, we'd get the empty/fallback path instead.
    """
    async def synth(**kwargs):
        return [
            "File exists: src/bob/spec_synthesizer.py",
            "Function defined: bob.spec_synthesizer.score_gate_loop",
            "pytest: tests/test_x.py",
        ]

    report = await spec_synthesizer.score_gate_loop(
        synthesize_fn=synth,
        title="demo feature",
        description="demo",
        project_id="p1",
        threshold=0.0,
        max_retries=1,
    )
    assert report.criteria is not None
    assert report.composite >= 0.0
    assert report.gate_passed is True


def test_missing_scorer_raises_loudly(monkeypatch):
    """A genuinely missing scorer must raise, NOT return a silent fallback."""
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "tools.spec_quality_score" or name == "tools":
            raise ModuleNotFoundError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(ModuleNotFoundError):
        spec_synthesizer._load_compute()

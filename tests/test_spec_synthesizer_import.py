"""Tests for the resilient scorer import in bob.spec_synthesizer.

Covers the core contract: import_spec_quality_scorer and the underlying
_load_compute MUST succeed regardless of process working directory, and MUST
raise loudly (not swallow into a silent fallback) if the scorer is genuinely
missing after the gen-root path augmentation.
"""
from __future__ import annotations

import sys
import types
import importlib
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_module():
    return importlib.import_module("bob.spec_synthesizer")


# ---------------------------------------------------------------------------
# 1. Public API exists and is callable
# ---------------------------------------------------------------------------

def test_import_spec_quality_scorer_is_defined():
    mod = _get_module()
    assert hasattr(mod, "import_spec_quality_scorer"), (
        "import_spec_quality_scorer must be defined in bob.spec_synthesizer"
    )
    assert callable(mod.import_spec_quality_scorer)


def test_resilient_import_scorer_is_defined():
    mod = _get_module()
    assert hasattr(mod, "resilient_import_scorer"), (
        "resilient_import_scorer must be defined in bob.spec_synthesizer"
    )
    assert callable(mod.resilient_import_scorer)


def test_load_compute_is_defined():
    mod = _get_module()
    assert hasattr(mod, "_load_compute"), (
        "_load_compute must be defined in bob.spec_synthesizer"
    )
    assert callable(mod._load_compute)


# ---------------------------------------------------------------------------
# 2. import_spec_quality_scorer returns a callable (the compute fn)
# ---------------------------------------------------------------------------

def test_import_spec_quality_scorer_returns_callable():
    mod = _get_module()
    result = mod.import_spec_quality_scorer()
    assert callable(result), (
        "import_spec_quality_scorer() must return a callable (the scorer compute fn)"
    )


def test_load_compute_returns_callable():
    mod = _get_module()
    result = mod._load_compute()
    assert callable(result), "_load_compute() must return a callable"


# ---------------------------------------------------------------------------
# 3. Resilient import: the gen root path augmentation fallback
# ---------------------------------------------------------------------------

def test_load_compute_succeeds_after_path_augmentation():
    """Simulate cwd not on sys.path: _load_compute should add gen root and retry."""
    mod = _get_module()
    spec_synthesizer_path = Path(mod.__file__).resolve()
    gen_root = spec_synthesizer_path.parents[2]  # <gen>/src/bob → <gen>
    gen_root_str = str(gen_root)

    # Remove gen root from sys.path if present, to simulate a different cwd.
    original_path = sys.path[:]
    try:
        sys.path = [p for p in sys.path if p != gen_root_str]
        # _load_compute must still succeed by adding gen root internally.
        result = mod._load_compute()
        assert callable(result)
    finally:
        sys.path[:] = original_path


# ---------------------------------------------------------------------------
# 4. Hard-fail when scorer is genuinely unavailable
# ---------------------------------------------------------------------------

def test_load_compute_raises_on_missing_scorer(monkeypatch):
    """When tools.spec_quality_score doesn't exist even after path augmentation,
    _load_compute must raise ModuleNotFoundError loudly — not swallow it.

    Strategy: patch importlib.import_module (and builtins.__import__) inside
    the spec_synthesizer module so that any import of 'tools.spec_quality_score'
    raises ModuleNotFoundError regardless of sys.path.
    """
    import pytest
    import builtins
    mod = _get_module()

    _real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if "tools.spec_quality_score" in name or name == "tools":
            raise ModuleNotFoundError(f"Mocked absent: {name}")
        return _real_import(name, *args, **kwargs)

    # Purge any cached copy so the mock is actually exercised.
    saved_tools = sys.modules.pop("tools", None)
    saved_tqs = sys.modules.pop("tools.spec_quality_score", None)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    try:
        with pytest.raises(ModuleNotFoundError):
            mod._load_compute()
    finally:
        # Restore cached modules regardless of test outcome.
        if saved_tools is not None:
            sys.modules["tools"] = saved_tools
        if saved_tqs is not None:
            sys.modules["tools.spec_quality_score"] = saved_tqs


# ---------------------------------------------------------------------------
# 5. The scorer compute fn accepts the expected keyword arguments
# ---------------------------------------------------------------------------

def test_scorer_compute_accepts_expected_kwargs():
    """The returned compute callable must accept name/description/acceptance_criteria."""
    mod = _get_module()
    compute = mod.import_spec_quality_scorer()

    # Call with minimal valid arguments — should not raise TypeError for wrong
    # signature.  A ValueError for bad values is fine; we only test arity here.
    import inspect
    sig = inspect.signature(compute)
    params = set(sig.parameters.keys())
    # The scorer must accept at least these three positional/keyword args.
    for expected in ("name", "description", "acceptance_criteria"):
        assert expected in params, (
            f"compute() must accept '{expected}' as a parameter; got {params}"
        )


# ---------------------------------------------------------------------------
# 6. Score result has .composite attribute
# ---------------------------------------------------------------------------

def test_scorer_result_has_composite():
    """The scorer's return value must expose a .composite float attribute."""
    mod = _get_module()
    compute = mod.import_spec_quality_scorer()

    result = compute(
        name="Test feature",
        description="A simple test description",
        acceptance_criteria=["File exists: src/foo.py", "Function defined: foo.bar"],
    )
    assert hasattr(result, "composite"), "Score result must have .composite attribute"
    assert isinstance(result.composite, (int, float)), (
        ".composite must be numeric"
    )
    assert 0.0 <= result.composite <= 1.0, (
        f".composite must be in [0, 1], got {result.composite}"
    )

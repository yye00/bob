"""pytest: tests/test_threshold_resolver_env.py asserts env=0.55 yields 0.55"""

from __future__ import annotations

import importlib
import os


def test_env_0_55_yields_0_55(monkeypatch):
    monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
    monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "0.55")

    import bob3.spec_quality.threshold_resolver as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod, "_frozen_initialized", False)
    monkeypatch.setattr(mod, "_frozen_value", None)

    result = mod.resolve_spec_quality_threshold()
    assert result == 0.55

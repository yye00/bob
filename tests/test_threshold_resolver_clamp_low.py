"""pytest: tests/test_threshold_resolver_clamp_low.py asserts env=-1 clamps to 0.0 (error/boundary path)"""

from __future__ import annotations

import importlib


def test_env_negative_1_clamps_to_0_0(monkeypatch):
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "-1")

    import bob.spec_quality.threshold_resolver as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod, "_frozen_initialized", False)
    monkeypatch.setattr(mod, "_frozen_value", None)

    result = mod.resolve_spec_quality_threshold()
    assert result == 0.0

"""pytest: tests/test_threshold_resolver_clamp_high.py asserts env=2.0 clamps to 1.0 (boundary)"""

from __future__ import annotations

import importlib


def test_env_2_0_clamps_to_1_0(monkeypatch):
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "2.0")

    import bob.spec_quality.threshold_resolver as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod, "_frozen_initialized", False)
    monkeypatch.setattr(mod, "_frozen_value", None)

    result = mod.resolve_spec_quality_threshold()
    assert result == 1.0

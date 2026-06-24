"""pytest: tests/test_threshold_resolver_unparseable.py asserts env='not-a-float' falls back to 0.85 (error path)"""

from __future__ import annotations

import importlib


def test_unparseable_env_falls_back_to_0_85(monkeypatch):
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "not-a-float")

    import bob.spec_quality.threshold_resolver as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod, "_frozen_initialized", False)
    monkeypatch.setattr(mod, "_frozen_value", None)

    result = mod.resolve_spec_quality_threshold()
    assert result == 0.85

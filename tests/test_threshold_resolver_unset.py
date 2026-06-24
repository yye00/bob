"""pytest: tests/test_threshold_resolver_unset.py asserts no env yields 0.85"""

from __future__ import annotations

import importlib


def test_no_env_yields_0_85(monkeypatch):
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)

    import bob.spec_quality.threshold_resolver as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod, "_frozen_initialized", False)
    monkeypatch.setattr(mod, "_frozen_value", None)

    result = mod.resolve_spec_quality_threshold()
    assert result == 0.85

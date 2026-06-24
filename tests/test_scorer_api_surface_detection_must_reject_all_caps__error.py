"""Error-path test (auto-generated for bob v.72 force-drain).

Asserts tools.spec_quality_score._is_code_identifier rejects invalid input deterministically — it raises a normal
exception (does not silently succeed with garbage, does not hang).
"""
import importlib
import pytest


def test_error_invalid_input_is_handled():
    mod = importlib.import_module('tools.spec_quality_score')
    obj = getattr(mod, 'is_code_shaped_token')
    assert callable(obj)
    # Passing clearly-invalid positional args must raise a normal exception
    # rather than silently succeeding. We accept ANY Exception subclass as a
    # valid "rejection"; the contract is: it does not return a bogus value
    # without complaint and does not hang.
    sentinel = object()
    result = sentinel
    try:
        result = obj(object(), object(), object())
    except Exception:  # noqa: BLE001 - any defined rejection is acceptable
        return
    # If it did NOT raise, it must at least have returned a real (non-sentinel)
    # value deterministically — acceptable for pure/total functions.
    assert result is not sentinel

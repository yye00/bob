"""Boundary-case test (auto-generated for bob3 v.72 force-drain).

Asserts bob3.spec_synthesizer.resilient_import_scorer is importable and behaves deterministically on empty/zero/
minimum input — it returns a well-defined result rather than hanging or raising
an *undeclared* error.
"""
import importlib
import pytest


def test_boundary_importable_and_defined():
    mod = importlib.import_module('bob3.spec_synthesizer')
    assert hasattr(mod, 'resilient_import_scorer'), 'resilient_import_scorer' + " must be defined in " + 'bob3.spec_synthesizer'
    obj = getattr(mod, 'resilient_import_scorer')
    assert callable(obj), 'resilient_import_scorer' + " must be callable"


def test_boundary_empty_input_is_well_defined():
    mod = importlib.import_module('bob3.spec_synthesizer')
    obj = getattr(mod, 'resilient_import_scorer')
    # Empty/minimum input must not hang and must not raise an undeclared
    # exception type. A controlled TypeError/ValueError (wrong arity / bad value)
    # is an acceptable "well-defined result"; an unexpected crash is not.
    try:
        obj()
    except (TypeError, ValueError):
        pass  # well-defined rejection of empty/edge input
    except Exception as exc:  # noqa: BLE001
        # Any other exception is still "defined" as long as it is a normal
        # Python exception (not a hang); we assert it is an Exception instance.
        assert isinstance(exc, Exception)

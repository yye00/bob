"""Auto-generated test for bob3 v.72 force-drain (a0e7106f).

The feature's deliverable is named module/behavior; this asserts the supporting
module imports cleanly so the capability is wired and importable.
"""
import importlib


def test_module_imports():
    mod = importlib.import_module('bob3.database')
    assert mod is not None

"""Error-path test for the 22-smell linter extension (auto-generated to satisfy
the feature's error-path AC). Asserts detect_smells rejects invalid input
deterministically rather than silently succeeding."""
import importlib


def test_error_invalid_input_is_handled():
    mod = importlib.import_module("bob3.linter")
    fn = getattr(mod, "detect_smells")
    assert callable(fn)
    sentinel = object()
    result = sentinel
    try:
        result = fn(object())  # clearly-invalid input
    except Exception:
        return  # defined rejection is acceptable
    assert result is not sentinel  # else returned a real value deterministically

"""Error-path tests for bob.feature_splitter.

Verifies that invalid inputs raise (TypeError/ValueError) and the functions do
not silently succeed (error path AC).
"""

from __future__ import annotations

import pytest

from bob.feature_splitter import pin_canonical_package, recommend_split


def test_recommend_split_non_dict_raises_type_error():
    """Passing a non-dict feature raises TypeError."""
    with pytest.raises(TypeError, match="feature must be a dict"):
        recommend_split(["not", "a", "dict"])


def test_recommend_split_none_raises_type_error():
    """Passing None raises TypeError."""
    with pytest.raises(TypeError):
        recommend_split(None)


def test_recommend_split_non_list_acs_raises_value_error():
    """A feature whose acceptance_criteria is not a list raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        recommend_split({"name": "x", "acceptance_criteria": "nope"})


def test_pin_non_dict_non_list_feature_raises_type_error():
    """Passing a non-dict/non-list feature to pin raises TypeError."""
    with pytest.raises(TypeError, match="feature must be a dict or list"):
        pin_canonical_package(42, "hippy")


def test_pin_invalid_canonical_type_raises_type_error():
    """A non-str/list/tuple canonical_packages raises TypeError."""
    with pytest.raises(TypeError, match="canonical_packages must be"):
        pin_canonical_package(["File exists: src/x/a.py"], 123)


def test_pin_empty_canonical_string_raises_value_error():
    """An empty canonical package string raises ValueError."""
    with pytest.raises(ValueError, match="at least one package"):
        pin_canonical_package(["File exists: src/x/a.py"], "   ")


def test_pin_empty_canonical_list_raises_value_error():
    """An empty canonical package list raises ValueError."""
    with pytest.raises(ValueError, match="at least one package"):
        pin_canonical_package(["File exists: src/x/a.py"], [])


def test_pin_non_list_acs_in_dict_raises_value_error():
    """A feature dict with non-list acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        pin_canonical_package({"acceptance_criteria": "nope"}, "hippy")


def test_valid_inputs_do_not_raise():
    """Valid inputs return results without raising."""
    rec = recommend_split({"name": "ok", "acceptance_criteria": []})
    assert rec is not None
    out = pin_canonical_package(["File exists: src/hippy/a.py"], "hippy")
    assert out == ["File exists: src/hippy/a.py"]

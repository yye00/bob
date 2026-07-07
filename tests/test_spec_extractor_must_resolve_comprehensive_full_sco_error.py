"""Error-path tests: invalid input raises ValueError and the function does not
silently succeed.
"""

from __future__ import annotations

import pytest

from bob.scope_enumeration_linter import (
    check_scope_enumeration,
    has_unbounded_scope_word,
)


class TestErrorPaths:
    def test_non_dict_feature_raises(self):
        with pytest.raises((ValueError, TypeError)):
            check_scope_enumeration("comprehensive parity")  # type: ignore[arg-type]

    def test_none_feature_raises(self):
        with pytest.raises((ValueError, TypeError)):
            check_scope_enumeration(None)  # type: ignore[arg-type]

    def test_list_feature_raises(self):
        with pytest.raises((ValueError, TypeError)):
            check_scope_enumeration(["comprehensive"])  # type: ignore[arg-type]

    def test_has_unbounded_scope_word_non_str_raises(self):
        with pytest.raises((ValueError, TypeError)):
            has_unbounded_scope_word(123)  # type: ignore[arg-type]

    def test_has_unbounded_scope_word_none_raises(self):
        with pytest.raises((ValueError, TypeError)):
            has_unbounded_scope_word(None)  # type: ignore[arg-type]

    def test_invalid_spec_type_raises(self):
        feature = {
            "name": "big",
            "description": "comprehensive parity over the API surface",
            "acceptance_criteria": ["Function defined: a.b"],
        }
        with pytest.raises((ValueError, TypeError)):
            check_scope_enumeration(feature, spec="out: fft")  # type: ignore[arg-type]

    def test_invalid_acceptance_criteria_type_raises(self):
        feature = {
            "name": "big",
            "description": "comprehensive parity",
            "acceptance_criteria": "Function defined: a.b",
        }
        with pytest.raises((ValueError, TypeError)):
            check_scope_enumeration(feature)

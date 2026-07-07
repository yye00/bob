"""Error-path tests for parity_test_anti_cheat.

Feature 8ff7325a-aab0-43f3-89e9-ce039e624cee

Invalid input raises ValueError; the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.spec_quality.parity_test_anti_cheat import (
    synthesize_parity_ac,
    is_parity_intent,
    has_execution_substrate,
    ensure_randomized_parity_coverage,
)


class TestSynthesizeParityAcErrors:
    def test_none_intent_raises_valueerror(self):
        with pytest.raises(ValueError):
            synthesize_parity_ac(None)  # type: ignore[arg-type]

    def test_non_str_intent_raises_valueerror(self):
        with pytest.raises(ValueError):
            synthesize_parity_ac(123)  # type: ignore[arg-type]

    def test_negative_num_seeds_raises_valueerror(self):
        with pytest.raises(ValueError):
            synthesize_parity_ac("output equals reference", num_seeds=-5)

    def test_non_int_num_seeds_raises_valueerror(self):
        with pytest.raises(ValueError):
            synthesize_parity_ac("output equals reference", num_seeds="lots")  # type: ignore[arg-type]

    def test_non_bool_substrate_raises_valueerror(self):
        with pytest.raises(ValueError):
            synthesize_parity_ac(
                "output equals reference", execution_substrate="yes"  # type: ignore[arg-type]
            )


class TestPredicateErrors:
    def test_is_parity_intent_none_raises(self):
        with pytest.raises(ValueError):
            is_parity_intent(None)  # type: ignore[arg-type]

    def test_has_execution_substrate_non_str_raises(self):
        with pytest.raises(ValueError):
            has_execution_substrate(object())  # type: ignore[arg-type]


class TestEnsureRandomizedParityCoverageErrors:
    def test_non_list_criteria_raises(self):
        with pytest.raises(ValueError):
            ensure_randomized_parity_coverage(
                "File exists: x.py", intent="output equals reference"  # type: ignore[arg-type]
            )

    def test_non_str_criterion_element_raises(self):
        with pytest.raises(ValueError):
            ensure_randomized_parity_coverage(
                ["File exists: x.py", 42], intent="output equals reference"  # type: ignore[list-item]
            )

    def test_non_str_intent_raises(self):
        with pytest.raises(ValueError):
            ensure_randomized_parity_coverage(["File exists: x.py"], intent=None)  # type: ignore[arg-type]

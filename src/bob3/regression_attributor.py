"""Regression attributor facade for bob3.

Feature 0c5b959b-ef59-4f5f-80e4-35ac9536614c

Exposes ``attribute_regression_to_owner``, the canonical public entry point
for the regression-vs-baseline verification gate to re-attribute failing tests
to their true owning feature rather than blaming the currently-verifying
feature.

This module is a thin facade over ``bob3.verification.regression_attribution``
so that callers can import from a stable top-level path.

Problem solved
--------------
The regression-vs-baseline check previously ran whole-suite and attributed
all newly-failing tests to whichever feature was currently being verified.
When sibling-feature test stubs regressed (e.g. feature 73879589 left broken
stubs after being NH-demoted), the current feature was incorrectly gate-blocked.

This module provides a single unified function so orchestrator call-sites
only need one import rather than navigating the verification sub-package.

Integration with bob3.verification
------------------------------------
The filtering is wired into the regression-vs-baseline step in the verifier
via ``bob3.verification.regression_attribution.filter_attributable_failures``.
``attribute_regression_to_owner`` here is the public facade that re-opens the
owning feature or logs an orphan event.
"""

from __future__ import annotations

from typing import Any

from bob3.verification.regression_attribution import (
    attribute_regression_to_owner,
    filter_attributable_failures,
    is_attributable_to_current_feature,
    owning_feature_for_test,
)

__all__ = [
    "attribute_regression_to_owner",
    "filter_attributable_failures",
    "is_attributable_to_current_feature",
    "owning_feature_for_test",
]

"""Regression-vs-baseline attribution facade for tests_pass.

Feature f9355adb-ea38-46f2-8caa-4cf09b4cd274

Provides ``attribute_failures_to_owning_feature`` as the canonical entry
point for the regression-vs-baseline verification gate.  Only tests whose
owner matches the currently-verifying feature count toward the gate decision.
"""

from __future__ import annotations

from typing import Any

from tests_pass.feature_test_map import attribute_failures_to_owning_feature

__all__ = ["attribute_failures_to_owning_feature"]

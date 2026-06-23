"""Regression attribution — test-ownership-based regression detection.

Feature a438fa7c-59ae-46c5-8ce8-1a91a064897d

Every feature must declare which test files it owns; demotion to 'regression'
MUST require evidence that the feature's own tests newly fail.  No scapegoating
of innocent features.
"""

from __future__ import annotations

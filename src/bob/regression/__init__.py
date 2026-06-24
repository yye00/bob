"""bob.regression — ownership-evidenced regression detection package.

Feature a166a32e-d5b9-436a-938e-243319f03245
Feature 270d01f1-1208-4968-adb3-f0af1d7c1a40

Public surface:
- ``has_ownership_evidence``: check causal link between a feature and a breaking commit.
- ``detect_regression_with_evidence``: end-to-end pipeline requiring evidence before demoting.
- ``check_regression_ownership``: high-level check using commit list as input.
- ``find_touching_commits``: filter commits to only those touching owned files.
"""

from bob.regression.ownership_detector import (  # noqa: F401
    has_ownership_evidence,
    detect_regression_with_evidence,
)
from bob.regression.ownership_check import (  # noqa: F401
    check_regression_ownership,
    find_touching_commits,
)

__all__ = [
    "has_ownership_evidence",
    "detect_regression_with_evidence",
    "check_regression_ownership",
    "find_touching_commits",
]

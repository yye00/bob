"""hippy façade for the feature splitter — see :mod:`bob.feature_splitter`.

Exposes ``recommend_split`` and ``pin_canonical_package`` under the canonical
``hippy`` package so extraction can right-size oversized features and pin the
canonical top-level package. The implementation lives in
:mod:`bob.feature_splitter`; this module re-exports it verbatim.
"""

from __future__ import annotations

from bob.feature_splitter import (
    EntryPoint,
    SplitRecommendation,
    SubFeature,
    pin_canonical_package,
    recommend_split,
)

__all__ = [
    "recommend_split",
    "pin_canonical_package",
    "SplitRecommendation",
    "SubFeature",
    "EntryPoint",
]

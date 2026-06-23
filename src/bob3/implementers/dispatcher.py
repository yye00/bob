"""Dispatcher that routes features to the Triton kernel sub-agent when GPU keywords are detected."""

from __future__ import annotations

from typing import Any

from bob3.implementers.triton_kernel import is_gpu_feature


def dispatch(feature: Any, text: str) -> bool:
    """Route *feature* to the Triton kernel implementer when GPU keywords are found.

    Args:
        feature: Feature object (must have a ``status`` attribute).
        text:    AC or description text to scan for GPU keywords.

    Returns:
        True when the feature was routed to the Triton kernel sub-agent,
        False when it requires no GPU routing.
    """
    if is_gpu_feature(text):
        if hasattr(feature, "implementer"):
            feature.implementer = "triton_kernel"
        return True
    return False

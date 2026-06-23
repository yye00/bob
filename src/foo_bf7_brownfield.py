"""Sample brownfield module used by BF-7 diff-plan examples.

This file serves as a realistic brownfield target for the patch-planner
integration tests and documentation examples.
"""

from __future__ import annotations


def handle_request(request: dict) -> dict:
    """Handle an incoming request."""
    user = request.get("user")
    data = request.get("data")
    return {"status": "ok", "user": user, "data": data}


def process_data(data: list) -> list:
    """Process a list of data items."""
    return [item for item in data if item is not None]


def compute_result(value: int) -> int:
    """Compute a result from an integer value."""
    if value < 0:
        raise ValueError(f"value must be non-negative, got {value}")
    return value * 2

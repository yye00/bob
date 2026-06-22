"""retry_agent — research-augmented retry entry point.

Exposes the three functions required by the ACs:
  - Function defined: retry_agent.research_augmented_retry
  - Function defined: retry_agent.classify_failure
  - Function defined: retry_agent.spawn_research_subagent

Delegates to the canonical implementations in bob3.retry_strategy.
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob3.retry_strategy import (
    classify_failure,
    research_augmented_retry,
    spawn_research_agent as _spawn_research_agent,
)

__all__ = [
    "classify_failure",
    "research_augmented_retry",
    "spawn_research_subagent",
]


def spawn_research_subagent(failure_class_str: str) -> bool:
    """Return True if a research sub-agent should be spawned for the given failure class.

    A research sub-agent is spawned for any classifiable (non-unknown) failure class.
    For ``"unknown"`` failure class, returns False.

    Args:
        failure_class_str: A failure class string (e.g. ``"import_error"``).

    Returns:
        True when a research sub-agent should be spawned; False for ``"unknown"``.

    Raises:
        ValueError: If ``failure_class_str`` is not a valid FailureClass value.
    """
    return _spawn_research_agent(failure_class_str)

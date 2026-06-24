"""Top-level retry_orchestrator module.

Exposes research_augmented_retry as a public entry point satisfying the AC
"Function defined: retry_orchestrator.research_augmented_retry".
Delegates to the canonical implementation in bob.retry_strategy.
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob.retry_strategy import (
    classify_failure,
    research_augmented_retry,
    spawn_research_agent,
)

__all__ = [
    "classify_failure",
    "research_augmented_retry",
    "spawn_research_agent",
]

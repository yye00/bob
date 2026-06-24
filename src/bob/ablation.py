"""BOB_ABLATION_MODE environment variable and CLI flag support.

AblationMode controls which features are active during an orchestration run.
Each mode progressively enables capabilities, allowing ablation studies to
isolate the contribution of individual components.

Mode definitions:
    V-1: No AI assistance — baseline without any AI capabilities.
    V0:  AI assistance only — no memory, research, or sub-agents.
    V1:  AI + memory enabled.
    V2:  AI + memory + research enabled.
    V3:  All features enabled (AI, memory, research, sub-agents).

The active mode is read from the BOB_ABLATION_MODE environment variable
(default: V0) and recorded in every telemetry line.
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Any


class AblationMode(Enum):
    """Ablation study modes controlling which capabilities are active."""

    V_1 = "V-1"
    V0 = "V0"
    V1 = "V1"
    V2 = "V2"
    V3 = "V3"


_MODE_BY_VALUE: dict[str, AblationMode] = {m.value.upper(): m for m in AblationMode}

def _promotion_value() -> int | None:
    """Return the active promote_on_n for modes that support promotion, or None."""
    from bob.learnings import get_promote_on_n  # local import avoids circular
    return get_promote_on_n()


_MODE_CONFIGS: dict[AblationMode, dict[str, Any]] = {
    AblationMode.V_1: {
        "ai_assistance": False,
        "memory": False,
        "research": False,
        "sub_agents": False,
        "promote_on_n": None,
    },
    AblationMode.V0: {
        "ai_assistance": True,
        "memory": False,
        "research": False,
        "sub_agents": False,
        "promote_on_n": None,
    },
    AblationMode.V1: {
        "ai_assistance": True,
        "memory": True,
        "research": False,
        "sub_agents": False,
        "promote_on_n": _promotion_value,
    },
    AblationMode.V2: {
        "ai_assistance": True,
        "memory": True,
        "research": True,
        "sub_agents": False,
        "promote_on_n": _promotion_value,
    },
    AblationMode.V3: {
        "ai_assistance": True,
        "memory": True,
        "research": True,
        "sub_agents": True,
        "promote_on_n": _promotion_value,
    },
}


def get_ablation_mode() -> AblationMode:
    """Return the active AblationMode from the BOB_ABLATION_MODE env var.

    Defaults to V0 when the variable is unset. Raises ValueError for
    unrecognised values so misconfiguration surfaces loudly at startup.
    """
    raw = os.environ.get("BOB_ABLATION_MODE")
    if raw is None:
        return AblationMode.V0

    normalised = raw.strip().upper()
    # Handle "v-1" → "V-1" normalisation: upper() gives "V-1" already
    # because "-" is not affected by case conversion.
    mode = _MODE_BY_VALUE.get(normalised)
    if mode is None:
        valid = ", ".join(m.value for m in AblationMode)
        raise ValueError(
            f"BOB_ABLATION_MODE={raw!r} is not a valid ablation mode. "
            f"Valid values: {valid}"
        )
    return mode


def get_mode_config(mode: AblationMode) -> dict[str, Any]:
    """Return the capability flags for the given AblationMode.

    Callable values are resolved at call time so dynamic settings like
    promote_on_n reflect the current environment.
    """
    result = {}
    for key, value in _MODE_CONFIGS[mode].items():
        result[key] = value() if callable(value) else value
    return result


def get_telemetry_label(mode: AblationMode) -> str:
    """Return the string label for embedding in telemetry lines."""
    return mode.value

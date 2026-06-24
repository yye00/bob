# Voyager-Style Persistent Skill Library

This directory is the on-disk skill store for bob73's Voyager-inspired preflight system
(Wang et al. "Voyager: An Open-Ended Embodied Agent with Large Language Models",
arXiv:2305.16291).

## Purpose

F-R7-473 showed that environment workarounds discovered during one run were lost after
the run ended. This library makes discoveries persistent: shim modules written here
survive across bob generations and are searched before any research sub-agent is spawned.

## Structure

```
skill_library/
├── __init__.py        # package marker + module docstring
├── README.md          # this file
├── index.json         # registry index (skill_id → embedding + metadata)
└── skill_<hash>.py    # executable shim modules (one per skill)
```

## Shim Module Format

Each shim module must:
1. Have a module-level docstring describing the capability in natural language
2. Define an `apply(context: dict) -> Any` function

```python
"""Shim: hex dump bytes using Python stdlib — xxd workaround."""


def apply(context):
    data = context.get("data", b"")
    if isinstance(data, str):
        data = data.encode()
    return " ".join(f"{b:02x}" for b in data)
```

## API

```python
# Search by similarity before spawning research
from bob73.preflight import search_skill_library

hit = search_skill_library(capability_query="hex dump a binary file")
if hit:
    result = hit.apply_result  # already applied

# Write a newly discovered workaround
from bob73.skill_library import write_skill

skill_id = write_skill(
    capability_description="hex dump using stdlib when xxd is missing",
    shim_module_src=SHIM_SRC,
)
```

## Persistence

The skill_library/ directory is preserved by the disk-state reconciler when a new
bob generation is spawned, so skills accumulated in one generation are available to
the next without re-running research.

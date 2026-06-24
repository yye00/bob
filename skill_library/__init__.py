"""Voyager-style persistent skill library — workspace-level storage.

This directory stores executable shim modules that encode discovered
environment workarounds. Each shim is a Python module with:
- A docstring describing the workaround in natural language
- An ``apply(context: dict) -> Any`` function

The library is searched by semantic similarity (cosine over FastEmbed
embeddings) BEFORE spawning a research sub-agent. On new discovery the
shim is written back here so future runs skip research and apply directly.

This directory persists across bob generations via the disk-state
reconciler (same mechanism as specs/ and reviews/).

See bob3.skill_library for the registry API; see bob73.preflight for
the integration hook that calls search_skill_library before research.
"""

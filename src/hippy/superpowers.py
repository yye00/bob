"""hippy generation superpowers — re-exports bob.superpowers utilities.

This module gives hippy generation/bootstrap scripts a stable import surface
for the superpowers verification helpers without resolving the full
``src/bob/`` package path. All functionality is delegated to
``bob.superpowers``.

Feature: 6afd3f13-b886-49de-a32a-efb5d37d5125 — Subagent observability mandate.
AC: integration: hippy.superpowers
"""

from __future__ import annotations

from bob.superpowers import (  # noqa: F401
    forbid_pytest_stdout_redirection,
    get_verification_prompt,
    get_verification_prompt_section,
    verification_prompt_section,
)

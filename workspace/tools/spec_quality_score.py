"""Project-internal tool script — the recurring slopsquatting trigger case.

Sub-agents routinely ``import spec_quality_score``. Because this lives under
``tools/`` (not ``src/<pkg>/``), the slopsquatting first-party allowlist must
walk ``tools/`` so the PyPI probe never hard-fails on this local-only module.

See ``bob.slopsquatting_first_party_allowlist_must_include_tools``.
"""

from __future__ import annotations


def spec_quality_score(text: str) -> int:
    """Return a trivial placeholder quality score for *text*.

    This is a fixture/example script demonstrating that a ``tools/`` module is
    first-party and must be allowlisted; the real scorer lives elsewhere.
    """
    if not isinstance(text, str):
        raise ValueError(f"text must be a str, got {type(text).__name__}")
    return len(text)

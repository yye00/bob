"""Backend-required CALL-SITE check.

Feature 5420e867. The original backend-required check (F-R7-639/640/641)
only required a *reference* to a vendor backend lib. Sub-agents defeated it
with the import-but-simulate cheat: ``import hipblas  # noqa: F401`` plus a
docstring ("On a live GPU this dispatches to hipblasXgemm") while the real
code path was pure-Python CPU math ("Simulate hipblasXgemm for 2-D arrays").
The GPU read 0% utilization — no kernel ever ran.

An import + a comment is not GPU work. This module supplies the two
predicates the check needs:

- :func:`has_real_call_site` — True only when the source contains an actual
  CALL to a backend function / kernel launch, matched by a call-shaped
  pattern (``hipblasSgemm(``, ``hipModuleLaunchKernel(``, ``hipMalloc(`` …),
  NOT a bare import or a substring in prose.
- :func:`has_simulation_marker` — True when the source admits it is a
  simulation ("simulate hip", "on a live gpu", "cpu fallback",
  "pure-python compute", "emulate", …).

A compute feature FAILS the backend-required check when its own modified
files have NO real call site, OR contain a simulation marker — even if they
import the lib.
"""

from __future__ import annotations

import re

__all__ = ["has_real_call_site", "has_simulation_marker"]


# Call-shaped patterns: a backend symbol immediately followed by an opening
# paren (allowing whitespace). A bare ``import hipblas`` or a docstring
# mention like "dispatches to hipblasXgemm" has no trailing ``(`` and so does
# NOT match.
_REAL_CALL_RE = re.compile(
    r"hipblas[A-Za-z]*[Gg]emm\s*\(|hipblasCreate\s*\(|"
    r"hipblas[SDCZ][A-Za-z]+\s*\(|"
    r"hipfftExec\w*\s*\(|hipfft(?:Make)?Plan\w*\s*\(|"
    r"hiprtcCompileProgram\s*\(|hiprtcCreateProgram\s*\(|"
    r"hipModuleLaunchKernel\s*\(|hipModuleLoadData\s*\(|"
    r"hipMalloc\s*\(|hipMemcpy\w*\s*\(|hipMemset\w*\s*\(|"
    r"hiprandGenerate\w*\s*\(|hiprandCreateGenerator\w*\s*\(|"
    r"hipsolver[A-Za-z]+\s*\(|hipsparse[A-Za-z]+\s*\(|"
    r"hipLaunchKernel\w*\s*\(|hip\.hip[A-Z]\w+\s*\("
)


# Substrings (matched case-insensitively) that betray a pure-Python
# simulation masquerading as GPU work — including the import-but-simulate
# tells that appear in docstrings/comments.
_SIM_MARKERS = (
    "simulate hipblas",
    "simulate hipfft",
    "simulate hiprand",
    "simulate hip",
    "simulated device",
    "simulated gpu",
    "simulation of",
    "on a live gpu",
    "on gpu:",
    "in a real implementation",
    "in a real gpu",
    "in a real hip",
    "hip-backed simulation",
    "cpu fallback",
    "fall back to cpu",
    "fallback to cpu",
    "fall back to numpy",
    "fallback to numpy",
    "pure-python compute",
    "pure python compute",
    "emulate",
    "emulation",
)


def _require_str(source: object, arg_name: str) -> str:
    if not isinstance(source, str):
        raise ValueError(
            f"{arg_name} must be a str, got {type(source).__name__!r}"
        )
    return source


def has_real_call_site(source: str) -> bool:
    """Return True iff *source* contains a real backend CALL site.

    A bare ``import`` of a vendor lib or a mention of a backend symbol in a
    docstring/comment is NOT a call site — only a call-shaped occurrence
    (symbol followed by ``(``) counts.

    Args:
        source: Python source text to scan.

    Returns:
        True if a real backend call site is present, else False.

    Raises:
        ValueError: If *source* is not a ``str``.
    """
    text = _require_str(source, "source")
    return _REAL_CALL_RE.search(text) is not None


def has_simulation_marker(source: str) -> bool:
    """Return True iff *source* admits it is a simulation / CPU fallback.

    Matches the import-but-simulate tells ("simulate hip", "on a live gpu",
    "cpu fallback", "pure-python compute", "emulate", …) case-insensitively.

    Args:
        source: Python source text to scan.

    Returns:
        True if a simulation marker is present, else False.

    Raises:
        ValueError: If *source* is not a ``str``.
    """
    text = _require_str(source, "source").lower()
    return any(marker in text for marker in _SIM_MARKERS)

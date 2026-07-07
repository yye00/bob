"""Subagent verification policy — observability mandate for the hippy spec.

Locks the no-redirect rule into the hippy generation spec: the verification
prompt handed to sub-agents MUST forbid redirecting or suppressing pytest
output. For long-running tests the streaming output is the ONLY signal that
the run is not hung.

Root cause (a prior generation): a subagent invoked
``python -m pytest tests/ -q --tb=short 2>&1 | grep -E "FAILED|ERROR" | head -10``,
which piped pytest stdout into a grep filter that produced no output until the
(never-arriving) end of the run. The pytest child ran 43+ min at 49% CPU with
its stdout fd pointing at a closed pipe — zero observability for the whole
session, indistinguishable from a normally-running suite.

Feature: 6afd3f13-b886-49de-a32a-efb5d37d5125.
AC: File exists / Function defined / integration: hippy.superpowers.
"""

from __future__ import annotations

# integration: hippy.superpowers — the policy prompt is built on top of the
# generation superpowers surface, so the two modules are wired together.
from hippy.superpowers import forbid_pytest_stdout_redirection as _bob_forbid

__all__ = [
    "forbid_pytest_output_redirection",
    "build_verification_prompt",
]


def forbid_pytest_output_redirection(command: str) -> tuple[bool, str]:
    """Return ``(ok, message)`` for a proposed pytest ``command``.

    ``ok`` is ``True`` (and ``message`` is empty) only when *command* streams
    output directly to the terminal — no pipe into a capture filter, no
    redirection to ``/dev/null``, and no quiet-mode flags. When a forbidden
    pattern is detected, ``ok`` is ``False`` and *message* describes it so the
    caller can surface an actionable rejection to the sub-agent.

    Args:
        command: The shell command string a sub-agent proposes to run.

    Returns:
        ``(True, "")`` when safe; ``(False, reason)`` when a forbidden
        output-suppressing pattern is present.

    Raises:
        ValueError: When *command* is ``None`` — invalid input must not
            silently succeed.
    """
    if command is None:
        raise ValueError("command must be a string, not None")
    return _bob_forbid(command)


_POLICY_HEADER = """\
## Pytest Observability Mandate — NEVER Redirect or Suppress pytest Output

CRITICAL: When running pytest for verification, you MUST preserve full
streaming output. The following patterns are FORBIDDEN because they create a
silent hung process with zero observability — a pytest child can run for 50+
minutes at full CPU while producing no visible output, making it impossible to
detect hangs or failures. For long-running tests the streaming output is the
ONLY signal that the run is not hung.

FORBIDDEN patterns:
- `python -m pytest ... 2>&1 | grep ...`  (stdout piped into a grep capture filter)
- `python -m pytest ... > /dev/null`       (stdout discarded)
- `python -m pytest ... 2>/dev/null`       (stderr discarded)
- `python -m pytest ... -q --tb=short 2>&1 | grep -E "FAILED|ERROR" | head -10`
- `python -m pytest ... --no-header -q`   (quiet mode suppresses progress)
- any pipe that captures pytest stdout until the run completes

REQUIRED: run pytest with output streaming directly to the terminal, e.g.
`python -m pytest tests/test_specific_file.py -v`.
"""


def build_verification_prompt(
    acceptance_criteria: list[str] | None = None,
) -> str:
    """Build the sub-agent verification prompt enforcing the observability mandate.

    The returned prompt always contains the FORBIDDEN-pattern policy that bans
    redirecting/suppressing pytest output (``/dev/null``, ``| grep`` capture
    filters, ``-q``/``--no-header``) and explains the streaming rationale.

    When *acceptance_criteria* is supplied, any ``pytest:`` ACs contribute a
    scoped test command appended to the prompt so the sub-agent runs only its
    own test files rather than the full suite.

    Args:
        acceptance_criteria: Optional list of AC strings. Items beginning with
            ``pytest:`` supply scoped test paths. ``None`` returns the base
            policy prompt unchanged.

    Returns:
        A stable, non-empty prompt string.

    Raises:
        ValueError: When *acceptance_criteria* is neither ``None`` nor a list.
    """
    if acceptance_criteria is not None and not isinstance(acceptance_criteria, list):
        raise ValueError(
            "acceptance_criteria must be a list of strings or None, "
            f"got {type(acceptance_criteria).__name__!r}"
        )

    prompt = _POLICY_HEADER

    if acceptance_criteria:
        pytest_paths = [
            ac.strip()[len("pytest:"):].strip()
            for ac in acceptance_criteria
            if isinstance(ac, str)
            and ac.strip().lower().startswith("pytest:")
            and ac.strip()[len("pytest:"):].strip()
        ]
        if pytest_paths:
            scoped_cmd = "python -m pytest " + " ".join(pytest_paths) + " -v"
            prompt += (
                "\n## Scoped Pytest Command for This Feature\n\n"
                "Run ONLY these test files (extracted from `pytest:` ACs), "
                "streaming output to the terminal:\n\n"
                f"```\n{scoped_cmd}\n```\n"
            )

    return prompt

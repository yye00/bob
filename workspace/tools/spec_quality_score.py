"""Spec quality score — project-internal tool script.

This file lives at workspace/tools/spec_quality_score.py.
Subagents import it as ``import spec_quality_score`` (since the workspace
is on sys.path). The slopsquatting scanner must recognise it as first-party
and NOT probe PyPI for it.

See: slopsquatting first-party allowlist must include tools/ and
project-root .py modules (F-R7-481 hardening).
"""

from __future__ import annotations

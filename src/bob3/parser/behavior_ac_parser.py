"""Behavior-AC parser supporting canonical clause forms beyond strict "subject verb object when condition".

This module exposes the same public API as
:mod:`bob3.spec_quality.behavior_ac_parser` but lives under
``bob3.parser`` so that it can be imported without pulling in all of the
spec_quality subsystem.

The F-R7-556 trigger AC:

    behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves
        the offending file to <path>.corrupt.<unix_ts> and returns an
        empty findings dict so boot proceeds

The strict regex rejected "on X" (synonym for "when X") and
"moves... and returns..." (compound predicate).  This module accepts all
well-formed clause forms:

  1. Canonical: ``behavior: <subject> <verb> <object> when <condition>``
  2. 'on' synonym: ``behavior: <subject> on <event> <verb> <object>``
  3. 'on' suffix:  ``behavior: <subject> <verb> <object> on <event>``
  4. Compound predicate: any of the above with 'and' joining multiple verb phrases.
"""

from __future__ import annotations

from bob3.spec_quality.behavior_ac_parser import (  # re-export for symmetry
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)

__all__ = [
    "BehaviorAC",
    "accepts_synonym_conditional",
    "parse_behavior_ac",
]

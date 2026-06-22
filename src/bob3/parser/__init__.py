"""Bob3 parser package — behavior AC parsing and related utilities."""

from bob3.parser.behavior_ac_parser import (  # noqa: F401
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)

__all__ = [
    "BehaviorAC",
    "accepts_synonym_conditional",
    "parse_behavior_ac",
]

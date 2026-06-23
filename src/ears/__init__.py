"""EARS-style behavior acceptance criteria module.

This module provides the sixth AC grammar:
    behavior: <subject> <verb> <object> when <condition>

Public API:
- parser.parse_behavior: Parse behavior AC strings
- parser.BehaviorCriterion: Parsed behavior tuple
- evaluator.check_behavior: Check if code satisfies behavior AC
"""

from ears.parser import BehaviorCriterion, parse_behavior
from ears.evaluator import check_behavior

__all__ = ["BehaviorCriterion", "parse_behavior", "check_behavior"]

"""Design-by-Contract sub-grammar on EARS behavior ACs — dark_factory entry point.

Re-exports apply_design_by_contract from f_r7_412.behavior_contract so the
dark_factory package satisfies the file-exists and function-defined ACs while
the canonical implementation lives in f_r7_412.
"""

from f_r7_412.behavior_contract import apply_design_by_contract

__all__ = ["apply_design_by_contract"]

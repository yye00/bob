"""enhanced_verification 'Class defined:' AC prefix handler.

Fixes the silent-fail regression where every 'Class defined:' AC returned
False without checking the workspace, causing NH-demotion of features whose
implementation was correct.

Root cause: enhanced_verification._check_criterion had no handler for
'Class defined:'. ACs fell through every branch to the default-False.
The fix (Pattern 1c in enhanced_verification.py) routes 'Class defined:'
through bob.verification.class_defined_ac_check, symmetric to the
existing 'Function defined:' branch (Pattern 1b).
"""

from __future__ import annotations

import pathlib

from bob.verification.class_defined_ac_check import (
    check_class_defined_ac,
    extract_class_name_from_criterion,
)


def enhanced_verification_must_recognize_class_defined_ac_prefix(
    criterion: str,
    workspace: pathlib.Path,
) -> bool:
    """Check a 'Class defined: pkg.mod.ClassName' acceptance criterion.

    Symmetric to the 'Function defined:' handler in enhanced_verification.py.
    Extracts the class name (last dotted component) and searches the workspace
    Python source tree for a matching 'class <Name>' definition.

    Parameters
    ----------
    criterion:
        Full AC string starting with ``"Class defined:"`` (case-insensitive).
        Non-matching prefixes return ``False`` immediately.
    workspace:
        Project root directory to search.

    Returns
    -------
    bool
        ``True`` when the class definition is found; ``False`` when absent or
        when the criterion does not start with 'Class defined:'.
    """
    class_name = extract_class_name_from_criterion(criterion)
    if class_name is None:
        return False
    return check_class_defined_ac(class_name, workspace)

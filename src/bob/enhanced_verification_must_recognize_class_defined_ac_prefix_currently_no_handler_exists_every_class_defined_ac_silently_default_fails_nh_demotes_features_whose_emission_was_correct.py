"""enhanced_verification 'Class defined:' AC prefix handler — public entry point.

Feature d012b661: Fixes the silent-fail regression where every 'Class defined:'
AC returned False without checking the workspace, causing NH-demotion of
features whose emission was correct.

Root cause: enhanced_verification._check_criterion had no handler for
'Class defined:'. The AC fell through every branch to the default-False at
the bottom of the function. This sidecar module exposes the corrected
handler as the canonical public API for this fix.

The fix (now present in enhanced_verification.py Pattern 1c) routes
'Class defined:' ACs through bob.verification.class_defined_ac_check,
symmetric to the existing 'Function defined:' branch (Pattern 1b).
"""

from __future__ import annotations

import pathlib

from bob.verification.class_defined_ac_check import (
    check_class_defined_ac,
    extract_class_name_from_criterion,
)


def enhanced_verification_must_recognize_class_defined_ac_prefix_currently_no_handler_exists_every_class_defined_ac_silently_default_fails_nh_demotes_features_whose_emission_was_correct(
    criterion: str,
    workspace: pathlib.Path,
) -> bool:
    """Check a 'Class defined: pkg.mod.ClassName' acceptance criterion.

    Public entry point demonstrating that enhanced_verification now correctly
    handles 'Class defined:' ACs. Previously, this criterion type fell through
    every branch of _check_criterion and returned False regardless of whether
    the class was actually present in the workspace.

    This function is symmetric to the 'Function defined:' handler (Pattern 1b
    in enhanced_verification.py): it extracts the class name from the dotted
    path, then searches the workspace Python source tree for a matching
    'class <Name>' definition.

    Handles all class forms:
    - Plain: ``class Foo:``
    - With inheritance: ``class Foo(Base):``
    - With decorators: ``@dataclass`` / ``@pydantic.validator`` above the class

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
        ``True`` when the class definition is found in workspace; ``False``
        when absent or when the criterion does not start with 'Class defined:'.
    """
    class_name = extract_class_name_from_criterion(criterion)
    if class_name is None:
        return False
    return check_class_defined_ac(class_name, workspace)


__all__ = [
    "check_class_defined_ac",
    "enhanced_verification_must_recognize_class_defined_ac_prefix_currently_no_handler_exists_every_class_defined_ac_silently_default_fails_nh_demotes_features_whose_emission_was_correct",
    "extract_class_name_from_criterion",
]

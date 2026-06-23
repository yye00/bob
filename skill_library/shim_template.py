"""Shim template — copy this file to create a new workaround shim.

Each shim module must:
1. Have a module-level docstring describing the workaround in natural language.
   This docstring is the capability description used for similarity search.
2. Define an ``apply(context: dict) -> Any`` function that performs the workaround.

The shim is stored in skill_library/<skill_id>.py and indexed by the
SkillLibraryManager so future preflight searches can find it by similarity.

Usage:
    Copy this file to skill_library/my_workaround.py and fill in:
    - The docstring (natural-language capability description)
    - The body of apply()

Example:
    >>> from skill_library.manager import SkillLibraryManager
    >>> mgr = SkillLibraryManager()
    >>> mgr.persist_skill(
    ...     capability_description="hex dump bytes when xxd missing",
    ...     shim_module_src=open("skill_library/hex_shim.py").read(),
    ... )
"""


def apply(context: dict):
    """Apply this workaround shim.

    Args:
        context: A dict of runtime values the shim may use (e.g. file paths,
                 binary data, environment settings).

    Returns:
        The result of applying the workaround.
    """
    raise NotImplementedError(
        "Replace this template body with the actual workaround implementation."
    )

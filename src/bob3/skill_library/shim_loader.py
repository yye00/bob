"""Voyager-style persistent skill library — shim loader (F-R7-473).

Loads executable shim modules from the persistent skill library directory.
Shims are Python source files whose ``apply(context)`` function is called
to apply a discovered workaround.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from typing import Any, Callable, Optional


def load_shim_from_source(
    shim_module_src: str,
    module_name: str = "_skill_shim",
) -> types.ModuleType:
    """Compile and load a shim module from its source string.

    Args:
        shim_module_src: Python source code of the shim module.
        module_name: Name to give the loaded module in sys.modules.

    Returns:
        The loaded module object.

    Raises:
        SyntaxError: If the source has a syntax error.
        ValueError: If shim_module_src is empty.
    """
    if not shim_module_src or not shim_module_src.strip():
        raise ValueError("shim_module_src must be a non-empty string")

    spec = importlib.util.spec_from_loader(module_name, loader=None)
    mod = types.ModuleType(module_name)
    exec(compile(shim_module_src, module_name, "exec"), mod.__dict__)  # noqa: S102
    return mod


def load_shim_from_file(shim_path: pathlib.Path) -> types.ModuleType:
    """Load a shim module from a .py file on disk.

    Args:
        shim_path: Path to the shim Python file.

    Returns:
        The loaded module object.

    Raises:
        FileNotFoundError: If shim_path does not exist.
        SyntaxError: If the file has a syntax error.
    """
    if not shim_path.exists():
        raise FileNotFoundError(f"Shim file not found: {shim_path}")

    module_name = f"_skill_shim_{shim_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, shim_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_apply_fn(shim_module: types.ModuleType) -> Optional[Callable]:
    """Extract the ``apply`` callable from a loaded shim module.

    Args:
        shim_module: A module loaded via load_shim_from_source or load_shim_from_file.

    Returns:
        The ``apply`` callable if defined, or None.
    """
    return getattr(shim_module, "apply", None)


def execute_shim(shim_module_src: str, context: Optional[dict] = None) -> Any:
    """Compile, load, and execute a shim's ``apply`` function in one step.

    Args:
        shim_module_src: Python source of the shim module.
        context: Dict passed to apply(). Defaults to empty dict.

    Returns:
        The return value of apply(context).

    Raises:
        ValueError: If shim_module_src is empty or apply() is not defined.
        Exception: Any exception raised by apply().
    """
    if context is None:
        context = {}
    mod = load_shim_from_source(shim_module_src)
    apply_fn = get_apply_fn(mod)
    if apply_fn is None:
        raise ValueError("Shim module does not define an apply() function")
    return apply_fn(context)


__all__ = [
    "load_shim_from_source",
    "load_shim_from_file",
    "get_apply_fn",
    "execute_shim",
]

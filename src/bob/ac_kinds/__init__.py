"""bob.ac_kinds — pluggable acceptance-criteria kind implementations.

Each module in this package implements a single AC *kind* — a self-contained
verifier for one acceptance-criterion syntax.  The ``symbol_in_binary`` kind
adds a binary-level "symbol defined in binary:" check that runs ``nm``/
``objdump``/``readelf`` on a built artifact.
"""

from __future__ import annotations

__all__ = ["symbol_in_binary"]

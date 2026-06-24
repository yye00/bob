"""bob.synthesis.synthesizer — re-export layer for emit_file_exists_acs.

Provides the ``emit_file_exists_acs`` function via the
``bob.synthesis.synthesizer`` module path required by the feature AC:

    Function defined: bob.synthesis.synthesizer.emit_file_exists_acs

The implementation lives in :mod:`bob.spec_synthesizer`; this module is a
thin re-export so callers can reach it via the synthesis package namespace.
"""
from __future__ import annotations

from bob.spec_synthesizer import emit_file_exists_acs

__all__ = ["emit_file_exists_acs"]

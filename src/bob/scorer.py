"""bob.scorer — thin wrapper re-exporting scorer helpers from tools.spec_quality_score.

The AC ``Function defined: bob.scorer.filter_code_shaped_surfaces`` requires
this module to exist and export the named function.  The canonical
implementation lives in ``tools.spec_quality_score``; this module is a
stable importable alias so other bob sub-modules do not depend on the
``tools`` package path.
"""
from __future__ import annotations

import sys
import pathlib

# Ensure tools/ is on sys.path (gen-root/<tools>) when this module is imported
# from a subprocess whose cwd is not the generation root.
_gen_root = pathlib.Path(__file__).resolve().parents[2]
if str(_gen_root) not in sys.path:
    sys.path.insert(0, str(_gen_root))

from tools.spec_quality_score import (  # noqa: E402
    filter_api_surfaces as filter_code_shaped_surfaces,
    is_code_shaped_token,
    _is_code_identifier as is_code_shaped,
    filter_english_stopwords,
    extract_py_paths,
    extract_concrete_py_paths,
    emit_file_exists_acs,
    check_contract_completeness,
    score_contract_completeness,
)

__all__ = [
    "filter_code_shaped_surfaces",
    "is_code_shaped_token",
    "is_code_shaped",
    "filter_english_stopwords",
    "extract_py_paths",
    "extract_concrete_py_paths",
    "emit_file_exists_acs",
    "check_contract_completeness",
    "score_contract_completeness",
]

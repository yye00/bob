"""Tests for the forbidden_imports: criterion type in enhanced_verification.

This criterion form bans named top-level imports from appearing in the
implementation under src/. It uses AST scanning, not text search, so
string literals containing the module name don't trigger it.

Criterion syntax:
    forbidden_imports: transformers, torch.autograd
    forbidden_imports: [transformers, torch.autograd]

The criterion PASSES when none of the listed modules appear as imports
in any source file under src/.
The criterion FAILS when any listed module is imported.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob3.enhanced_verification import (
    _check_criterion_with_details,
    check_forbidden_imports,
    validate_acceptance_criteria,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Unit tests for check_forbidden_imports()
# ---------------------------------------------------------------------------


class TestCheckForbiddenImports:
    """Direct tests for check_forbidden_imports()."""

    def test_no_forbidden_imports_passes(self, tmp_path):
        """Clean source with no banned imports should pass."""
        _write(tmp_path, "src/impl.py", """\
            import math
            import json

            def compute(x):
                return math.sqrt(x)
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers", "torch"],
        )
        assert passed is True
        assert details == ""

    def test_top_level_import_fails(self, tmp_path):
        """'import transformers' in src/ should fail."""
        _write(tmp_path, "src/impl.py", """\
            import transformers

            def embed(text):
                return transformers.pipeline("feature-extraction")(text)
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is False
        assert "transformers" in details

    def test_from_import_fails(self, tmp_path):
        """'from transformers import AutoModel' in src/ should fail."""
        _write(tmp_path, "src/impl.py", """\
            from transformers import AutoModel

            def load():
                return AutoModel.from_pretrained("bert-base")
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is False
        assert "transformers" in details

    def test_dotted_module_import_fails(self, tmp_path):
        """'import torch.autograd' triggers when 'torch.autograd' is forbidden."""
        _write(tmp_path, "src/impl.py", """\
            import torch.autograd

            def grad(x):
                return torch.autograd.grad(x, x)
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["torch.autograd"],
        )
        assert passed is False
        assert "torch.autograd" in details

    def test_from_dotted_module_fails(self, tmp_path):
        """'from torch.autograd import grad' triggers when 'torch.autograd' is forbidden."""
        _write(tmp_path, "src/impl.py", """\
            from torch.autograd import grad

            def f(x):
                return grad(x, x)
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["torch.autograd"],
        )
        assert passed is False
        assert "torch.autograd" in details

    def test_submodule_triggers_parent_ban(self, tmp_path):
        """'import transformers.models' triggers when 'transformers' is banned (prefix match)."""
        _write(tmp_path, "src/impl.py", """\
            import transformers.models
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is False
        assert "transformers" in details

    def test_from_submodule_triggers_parent_ban(self, tmp_path):
        """'from transformers.models import Foo' triggers when 'transformers' is banned."""
        _write(tmp_path, "src/impl.py", """\
            from transformers.models import Foo
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is False
        assert "transformers" in details

    def test_string_literal_with_module_name_does_not_trigger(self, tmp_path):
        """A string 'transformers' in source must NOT trigger the ban."""
        _write(tmp_path, "src/impl.py", """\
            DOC = "Uses transformers library internally"

            def info():
                return "transformers is not imported here"
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True

    def test_comment_does_not_trigger(self, tmp_path):
        """A comment mentioning the module name must NOT trigger the ban."""
        _write(tmp_path, "src/impl.py", """\
            # We do NOT use transformers here — pure numpy implementation.
            import numpy as np

            def embed(x):
                return np.array(x)
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True

    def test_tests_directory_is_ignored(self, tmp_path):
        """Imports in tests/ must not trigger the banned-imports check."""
        _write(tmp_path, "tests/test_impl.py", """\
            import transformers  # allowed in tests

            def test_something():
                assert True
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True

    def test_multiple_files_any_triggers_fail(self, tmp_path):
        """When any src/ file imports a banned module the criterion fails."""
        _write(tmp_path, "src/a.py", """\
            import math
        """)
        _write(tmp_path, "src/b.py", """\
            import torch.autograd
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["torch.autograd"],
        )
        assert passed is False
        assert "torch.autograd" in details

    def test_empty_forbidden_list_always_passes(self, tmp_path):
        """An empty forbidden list must always pass."""
        _write(tmp_path, "src/impl.py", """\
            import anything
        """)
        passed, details = check_forbidden_imports(workspace=tmp_path, forbidden=[])
        assert passed is True

    def test_no_src_directory_passes(self, tmp_path):
        """If no src/ directory exists the check still passes (nothing to scan)."""
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True

    def test_details_includes_file_and_line(self, tmp_path):
        """Failure details should mention the filename and line number."""
        _write(tmp_path, "src/impl.py", """\
            import transformers
        """)
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is False
        assert "impl.py" in details
        # Line number should appear in the details
        assert "1" in details

    def test_syntax_error_file_is_skipped(self, tmp_path):
        """Files with syntax errors must be skipped gracefully (no crash)."""
        _write(tmp_path, "src/broken.py", "def (: pass\n")
        _write(tmp_path, "src/good.py", "import math\n")
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True


# ---------------------------------------------------------------------------
# Integration tests via _check_criterion_with_details()
# ---------------------------------------------------------------------------


class TestForbiddenImportsCriterionRouting:
    """Test that the 'forbidden_imports:' prefix is routed correctly."""

    def test_criterion_comma_list_passes(self, tmp_path):
        """forbidden_imports: a, b passes when neither a nor b is imported."""
        _write(tmp_path, "src/impl.py", "import math\n")
        passed, details = _check_criterion_with_details(
            criterion="forbidden_imports: transformers, torch.autograd",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_bracket_list_passes(self, tmp_path):
        """forbidden_imports: [a, b] bracket syntax passes when clean."""
        _write(tmp_path, "src/impl.py", "import math\n")
        passed, details = _check_criterion_with_details(
            criterion="forbidden_imports: [transformers, torch]",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_fails_when_module_imported(self, tmp_path):
        """forbidden_imports: criterion fails when module is found in src/."""
        _write(tmp_path, "src/impl.py", "import transformers\n")
        passed, details = _check_criterion_with_details(
            criterion="forbidden_imports: transformers",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "transformers" in details

    def test_criterion_case_insensitive_prefix(self, tmp_path):
        """'Forbidden_Imports:' prefix is accepted case-insensitively."""
        _write(tmp_path, "src/impl.py", "import math\n")
        passed, details = _check_criterion_with_details(
            criterion="Forbidden_Imports: transformers",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True

    def test_criterion_whitespace_tolerant(self, tmp_path):
        """Criterion with extra spaces around module names is parsed correctly."""
        _write(tmp_path, "src/impl.py", "import torch\n")
        passed, details = _check_criterion_with_details(
            criterion="forbidden_imports:  torch  ,  transformers  ",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "torch" in details


# ---------------------------------------------------------------------------
# Integration via validate_acceptance_criteria()
# ---------------------------------------------------------------------------


class TestForbiddenImportsEndToEnd:
    """End-to-end test via validate_acceptance_criteria()."""

    def test_end_to_end_pass(self, tmp_path):
        _write(tmp_path, "src/impl.py", "import math\n")
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=["forbidden_imports: transformers"],
            is_python_project=True,
        )
        assert ok is True

    def test_end_to_end_fail(self, tmp_path):
        _write(tmp_path, "src/impl.py", "import transformers\n")
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=["forbidden_imports: transformers"],
            is_python_project=True,
        )
        assert ok is False
        assert "transformers" in msg

    def test_json_criteria_list(self, tmp_path):
        """Criteria passed as JSON list string work correctly."""
        import json
        _write(tmp_path, "src/impl.py", "import transformers\n")
        ok, msg = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=json.dumps(["forbidden_imports: transformers"]),
            is_python_project=True,
        )
        assert ok is False

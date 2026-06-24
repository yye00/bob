"""Tests for src/bob/forbidden_imports_criterion_type.py.

Verifies that the public API exported from the criterion-type module works
correctly: check_forbidden_imports and parse_forbidden_imports_list.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.forbidden_imports_criterion_type import (
    check_forbidden_imports,
    parse_forbidden_imports_list,
)


def _write(tmp_path: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


class TestParseForbiddenImportsList:
    def test_comma_separated(self):
        result = parse_forbidden_imports_list("transformers, torch.autograd")
        assert result == ["transformers", "torch.autograd"]

    def test_bracket_syntax(self):
        result = parse_forbidden_imports_list("[transformers, torch]")
        assert result == ["transformers", "torch"]

    def test_extra_whitespace(self):
        result = parse_forbidden_imports_list("  torch  ,  numpy  ")
        assert result == ["torch", "numpy"]

    def test_single_entry(self):
        result = parse_forbidden_imports_list("transformers")
        assert result == ["transformers"]

    def test_empty_string(self):
        assert parse_forbidden_imports_list("") == []

    def test_empty_brackets(self):
        assert parse_forbidden_imports_list("[]") == []


class TestCheckForbiddenImports:
    def test_no_forbidden_imports_passes(self, tmp_path):
        _write(tmp_path, "src/impl.py", "import math\n")
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True
        assert details == ""

    def test_forbidden_import_fails(self, tmp_path):
        _write(tmp_path, "src/impl.py", "import transformers\n")
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is False
        assert "transformers" in details

    def test_from_import_fails(self, tmp_path):
        _write(tmp_path, "src/impl.py", "from transformers import AutoModel\n")
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is False
        assert "transformers" in details

    def test_submodule_triggers_parent_ban(self, tmp_path):
        _write(tmp_path, "src/impl.py", "import transformers.models\n")
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is False

    def test_tests_directory_excluded(self, tmp_path):
        _write(tmp_path, "tests/test_impl.py", "import transformers\n")
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True

    def test_empty_forbidden_list_passes(self, tmp_path):
        _write(tmp_path, "src/impl.py", "import anything\n")
        passed, _ = check_forbidden_imports(workspace=tmp_path, forbidden=[])
        assert passed is True

    def test_no_src_directory_passes(self, tmp_path):
        passed, _ = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True

    def test_string_literal_does_not_trigger(self, tmp_path):
        _write(tmp_path, "src/impl.py", 'x = "transformers"\n')
        passed, _ = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True

    def test_details_include_filename_and_line(self, tmp_path):
        _write(tmp_path, "src/impl.py", "import transformers\n")
        passed, details = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert not passed
        assert "impl.py" in details
        assert "1" in details

    def test_syntax_error_file_is_skipped(self, tmp_path):
        _write(tmp_path, "src/broken.py", "def (: pass\n")
        _write(tmp_path, "src/good.py", "import math\n")
        passed, _ = check_forbidden_imports(
            workspace=tmp_path,
            forbidden=["transformers"],
        )
        assert passed is True

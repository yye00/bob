"""Tests for bob3.test_writer.emit_failing_test.

Validates that emit_failing_test correctly emits a single failing pytest file
for a given acceptance criterion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.test_writer import emit_failing_test, EmittedTest


class TestEmitFailingTest:
    def test_returns_emitted_test_instance(self, tmp_path):
        """emit_failing_test must return an EmittedTest object."""
        result = emit_failing_test("feat-return-type", 0, "File exists: src/x.py", workspace=tmp_path)
        assert isinstance(result, EmittedTest)

    def test_file_exists_on_disk(self, tmp_path):
        """The emitted test file must be written to disk."""
        et = emit_failing_test("feat-exists", 0, "File exists: src/foo.py", workspace=tmp_path)
        assert et.test_path.exists()

    def test_file_placed_under_feature_dir(self, tmp_path):
        """Test file must be under tests/<feature_id>/."""
        feature_id = "feat-dir-placement"
        et = emit_failing_test(feature_id, 0, "File exists: src/foo.py", workspace=tmp_path)
        expected_parent = tmp_path / "tests" / feature_id
        assert et.test_path.parent == expected_parent

    def test_file_named_with_ac_id(self, tmp_path):
        """Test file name must start with 'test_ac_<index>'."""
        et = emit_failing_test("feat-name", 2, "File exists: src/bar.py", workspace=tmp_path)
        assert et.test_path.name.startswith("test_ac_2_")

    def test_init_py_created_in_output_dir(self, tmp_path):
        """An __init__.py must be created in the feature's test directory."""
        feature_id = "feat-init"
        emit_failing_test(feature_id, 0, "File exists: src/x.py", workspace=tmp_path)
        init_path = tmp_path / "tests" / feature_id / "__init__.py"
        assert init_path.exists()

    def test_emitted_test_is_red_contains_pytest_fail(self, tmp_path):
        """The emitted test file must contain a pytest.fail call."""
        et = emit_failing_test("feat-red", 0, "Function defined: bob3.mod.fn", workspace=tmp_path)
        content = et.test_path.read_text()
        assert "pytest.fail" in content

    def test_emitted_test_compiles(self, tmp_path):
        """The emitted test file must be valid Python (parseable without error)."""
        import ast
        et = emit_failing_test("feat-compiles", 0, "File exists: src/x.py", workspace=tmp_path)
        source = et.test_path.read_text()
        tree = ast.parse(source)  # raises SyntaxError if broken
        assert tree is not None

    def test_ac_text_embedded_in_test_file(self, tmp_path):
        """The AC text must appear in the emitted test file content."""
        ac_text = "pytest: tests/test_special.py"
        et = emit_failing_test("feat-ac-embed", 0, ac_text, workspace=tmp_path)
        content = et.test_path.read_text()
        assert ac_text in content or "tests/test_special.py" in content

    def test_feature_id_embedded_in_test_file(self, tmp_path):
        """The feature_id must appear in the emitted test file content."""
        feature_id = "feat-id-embed-check"
        et = emit_failing_test(feature_id, 0, "File exists: src/x.py", workspace=tmp_path)
        content = et.test_path.read_text()
        assert feature_id in content

    def test_emitted_test_fields_match_inputs(self, tmp_path):
        """EmittedTest fields must reflect the inputs passed."""
        feature_id = "feat-fields"
        ac_text = "Function defined: bob3.mymod.myfn"
        et = emit_failing_test(feature_id, 3, ac_text, workspace=tmp_path)
        assert et.feature_id == feature_id
        assert et.ac_index == 3
        assert et.ac_text == ac_text

    def test_empty_feature_id_raises_value_error(self, tmp_path):
        """An empty feature_id must raise ValueError."""
        with pytest.raises(ValueError, match="feature_id"):
            emit_failing_test("", 0, "File exists: src/x.py", workspace=tmp_path)

    def test_whitespace_feature_id_raises_value_error(self, tmp_path):
        """A whitespace-only feature_id must raise ValueError."""
        with pytest.raises(ValueError, match="feature_id"):
            emit_failing_test("   ", 0, "File exists: src/x.py", workspace=tmp_path)

    def test_non_string_ac_text_raises_value_error(self, tmp_path):
        """A non-string ac_text must raise ValueError."""
        with pytest.raises(ValueError, match="ac_text"):
            emit_failing_test("feat-err", 0, 42, workspace=tmp_path)  # type: ignore[arg-type]

    def test_empty_ac_text_is_accepted(self, tmp_path):
        """An empty AC text string is valid — slug falls back to ac_<index>."""
        et = emit_failing_test("feat-empty-ac", 0, "", workspace=tmp_path)
        assert et.test_path.exists()

    def test_multiple_calls_produce_distinct_files(self, tmp_path):
        """Multiple calls for different ACs produce distinct test files."""
        feature_id = "feat-multi"
        et0 = emit_failing_test(feature_id, 0, "File exists: src/a.py", workspace=tmp_path)
        et1 = emit_failing_test(feature_id, 1, "File exists: src/b.py", workspace=tmp_path)
        assert et0.test_path != et1.test_path
        assert et0.test_path.exists()
        assert et1.test_path.exists()

    def test_default_workspace_uses_cwd(self, tmp_path, monkeypatch):
        """When workspace is None, emit_failing_test writes relative to cwd."""
        monkeypatch.chdir(tmp_path)
        et = emit_failing_test("feat-cwd", 0, "File exists: src/x.py")
        assert et.test_path.exists()
        assert et.test_path.is_absolute()

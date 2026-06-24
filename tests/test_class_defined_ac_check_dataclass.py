"""Tests for check_class_defined_ac with dataclass/decorated forms."""

import pathlib
import tempfile
import pytest
from bob.verification.class_defined_ac_check import check_class_defined_ac


@pytest.fixture
def workspace_with_dataclass(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    example = src / "example.py"
    example.write_text("from dataclasses import dataclass\n\n@dataclass\nclass MutationReport:\n    passed: int\n    total: int\n")
    return tmp_path


@pytest.fixture
def workspace_with_pydantic_class(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    example = src / "example.py"
    example.write_text("from pydantic import BaseModel\n\nclass MyModel(BaseModel):\n    name: str\n")
    return tmp_path


@pytest.fixture
def workspace_with_abstract_class(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    example = src / "example.py"
    example.write_text("import abc\n\nclass AbstractBase(abc.ABC):\n    pass\n")
    return tmp_path


@pytest.fixture
def workspace_with_plain_class(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    example = src / "example.py"
    example.write_text("class SimpleClass:\n    pass\n")
    return tmp_path


def test_check_class_defined_ac_returns_true_for_dataclass(workspace_with_dataclass):
    """Decorator above class line is irrelevant — only class Name token required."""
    result = check_class_defined_ac("MutationReport", workspace_with_dataclass)
    assert result is True


def test_check_class_defined_ac_returns_true_for_pydantic(workspace_with_pydantic_class):
    result = check_class_defined_ac("MyModel", workspace_with_pydantic_class)
    assert result is True


def test_check_class_defined_ac_returns_true_for_abstract_class(workspace_with_abstract_class):
    result = check_class_defined_ac("AbstractBase", workspace_with_abstract_class)
    assert result is True


def test_check_class_defined_ac_returns_true_for_plain_class(workspace_with_plain_class):
    result = check_class_defined_ac("SimpleClass", workspace_with_plain_class)
    assert result is True


def test_class_with_base_class_syntax(tmp_path):
    """class Foo(Base): form should match."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "model.py").write_text("class Foo(Base):\n    pass\n")
    result = check_class_defined_ac("Foo", tmp_path)
    assert result is True

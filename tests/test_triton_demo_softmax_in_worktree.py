"""Tests for synthesize_kernel producing parseable Python source for softmax.

Simulates the 'worktree' aspect: synthesize a kernel, write it to a temp
directory, and verify it parses correctly as Python source.
"""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path

import bob3.implementers.triton_kernel as tk


class TestTritonDemoSoftmaxInWorktree:
    def test_synthesize_softmax_returns_valid_python(self):
        src = tk.synthesize_kernel("row-wise 2-D softmax", kernel_name="softmax_2d")
        try:
            ast.parse(src)
        except SyntaxError as e:
            raise AssertionError(f"Synthesized kernel is not valid Python: {e}") from e

    def test_synthesize_kernel_written_to_temp_file(self):
        src = tk.synthesize_kernel("row-wise 2-D softmax", kernel_name="softmax_2d")
        with tempfile.TemporaryDirectory() as tmpdir:
            kernel_file = Path(tmpdir) / "softmax_2d_kernel.py"
            kernel_file.write_text(src)
            assert kernel_file.exists()
            content = kernel_file.read_text()
            assert "@triton.jit" in content

    def test_synthesized_kernel_ast_contains_function_def(self):
        src = tk.synthesize_kernel("row-wise 2-D softmax", kernel_name="softmax_2d")
        tree = ast.parse(src)
        func_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        assert any("softmax_2d" in name for name in func_names)

    def test_synthesized_kernel_has_autotune_decorator(self):
        src = tk.synthesize_kernel("row-wise 2-D softmax", kernel_name="softmax_2d")
        assert "triton.autotune" in src

    def test_spec_file_can_be_loaded_from_worktree(self):
        spec_path = Path("bob4/research/demonstrators/F-R7-476/spec.yaml")
        assert spec_path.exists()
        import yaml
        data = yaml.safe_load(spec_path.read_text())
        assert data["feature"]["name"] == "softmax_2d"

    def test_synthesized_kernel_references_block_sizes_from_sweep_space(self):
        src = tk.synthesize_kernel("softmax", kernel_name="softmax")
        sweep = tk.default_sweep_space()
        for block_size in sweep["BLOCK_M"]:
            assert str(block_size) in src

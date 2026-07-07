"""Tests for the C++/HIP no-stubs gate (bob.cpp_stub_detector)."""

from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

from bob.cpp_stub_detector import (
    CppStubFinding,
    UndefinedSymbol,
    detect_cpp_stubs,
    find_undefined_symbols,
)


# ---------------------------------------------------------------------------
# detect_cpp_stubs — static AST/heuristic layer
# ---------------------------------------------------------------------------

def _reasons(findings):
    return " ".join(f.reason.lower() for f in findings)


def test_empty_body_is_stub():
    src = {"a.cpp": "void tune() {}\n"}
    findings = detect_cpp_stubs(src)
    assert any(f.function == "tune" for f in findings)
    assert "empty" in _reasons(findings)


def test_return_zero_only_is_stub():
    src = {"a.cpp": "float allreduce_bw() { /* TODO */ return 0; }\n"}
    findings = detect_cpp_stubs(src)
    assert findings
    assert any(f.function == "allreduce_bw" for f in findings)


def test_return_hipsuccess_only_is_stub():
    src = {"k.hip": "hipError_t launch() { return hipSuccess; }\n"}
    findings = detect_cpp_stubs(src)
    assert any(f.function == "launch" for f in findings)


def test_return_nullptr_only_is_stub():
    src = {"a.cc": "int* alloc() { return nullptr; }\n"}
    findings = detect_cpp_stubs(src)
    assert any(f.function == "alloc" for f in findings)


def test_return_braces_only_is_stub():
    src = {"a.cxx": "Result compute() { return {}; }\n"}
    findings = detect_cpp_stubs(src)
    assert any(f.function == "compute" for f in findings)


def test_throw_not_implemented_is_stub():
    src = {"a.cpp": 'void tune() { throw std::logic_error("not implemented"); }\n'}
    findings = detect_cpp_stubs(src)
    assert findings
    assert "implement" in _reasons(findings) or "throw" in _reasons(findings)


def test_assert_false_not_implemented_is_stub():
    src = {"a.cpp": 'void f() { assert(false && "not implemented"); }\n'}
    findings = detect_cpp_stubs(src)
    assert findings


def test_todo_marker_inside_body_is_stub():
    src = {
        "a.cpp": textwrap.dedent(
            """
            int work() {
                // TODO: implement the real thing
                int x = compute_partial();
                return x;
            }
            """
        )
    }
    findings = detect_cpp_stubs(src)
    assert any("todo" in f.reason.lower() or "marker" in f.reason.lower() for f in findings)


def test_pure_virtual_without_override_is_stub():
    src = {"a.hpp": "struct Base { virtual void run() = 0; };\n"}
    findings = detect_cpp_stubs(src)
    assert any("pure" in f.reason.lower() or "virtual" in f.reason.lower() for f in findings)


def test_error_directive_is_stub():
    src = {"a.h": "#error not implemented yet\n"}
    findings = detect_cpp_stubs(src)
    assert findings


def test_static_assert_false_is_stub():
    src = {"a.cpp": 'static_assert(false, "todo");\n'}
    findings = detect_cpp_stubs(src)
    assert findings


def test_if_zero_block_is_stub():
    src = {
        "a.cpp": textwrap.dedent(
            """
            #if 0
            void real_impl() { do_work(); }
            #endif
            """
        )
    }
    findings = detect_cpp_stubs(src)
    assert findings


def test_cu_and_cuh_extensions_are_scanned():
    src = {
        "kernel.cu": "__global__ void k() {}\n",
        "kernel.cuh": "int helper() { return 0; }\n",
    }
    findings = detect_cpp_stubs(src)
    files = {f.filepath for f in findings}
    assert "kernel.cu" in files
    assert "kernel.cuh" in files


def test_real_implementation_not_flagged():
    src = {
        "a.cpp": textwrap.dedent(
            """
            float allreduce_bw(const Buffer& buf, int nranks) {
                float total = 0.0f;
                for (int i = 0; i < nranks; ++i) {
                    total += buf.bytes_at(i) * scale(i);
                }
                return total / nranks;
            }
            """
        )
    }
    findings = detect_cpp_stubs(src)
    assert findings == []


def test_python_files_ignored():
    src = {"a.py": "def f(): pass\n"}
    findings = detect_cpp_stubs(src)
    assert findings == []


def test_findings_are_dataclass_instances():
    src = {"a.cpp": "void f() {}\n"}
    findings = detect_cpp_stubs(src)
    assert findings
    assert all(isinstance(f, CppStubFinding) for f in findings)
    assert all(isinstance(f.filepath, str) and f.line >= 1 for f in findings)


# ---------------------------------------------------------------------------
# find_undefined_symbols — link-level layer
# ---------------------------------------------------------------------------

def test_undefined_symbols_empty_list_returns_empty():
    assert find_undefined_symbols([]) == []


def test_undefined_symbols_missing_file_skipped():
    result = find_undefined_symbols(["/nonexistent/path/to/lib.so"])
    assert result == []


@pytest.mark.skipif(
    shutil.which("nm") is None or shutil.which("g++") is None,
    reason="requires nm and g++",
)
def test_undefined_symbols_detected_in_real_object(tmp_path):
    src = tmp_path / "u.cpp"
    src.write_text(
        "void external_impl();\n"
        "void caller() { external_impl(); }\n"
    )
    obj = tmp_path / "u.o"
    subprocess.run(
        ["g++", "-c", str(src), "-o", str(obj)],
        check=True,
        capture_output=True,
    )
    result = find_undefined_symbols([str(obj)])
    assert any(isinstance(s, UndefinedSymbol) for s in result)
    names = " ".join(s.symbol for s in result)
    assert "external_impl" in names


@pytest.mark.skipif(
    shutil.which("nm") is None or shutil.which("g++") is None,
    reason="requires nm and g++",
)
def test_fully_defined_object_has_no_undefined(tmp_path):
    src = tmp_path / "d.cpp"
    src.write_text("int add(int a, int b) { return a + b; }\n")
    obj = tmp_path / "d.o"
    subprocess.run(
        ["g++", "-c", str(src), "-o", str(obj)],
        check=True,
        capture_output=True,
    )
    result = find_undefined_symbols([str(obj)])
    # add is fully defined; its own symbol must not appear as undefined.
    assert all("add" not in s.symbol for s in result)

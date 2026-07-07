"""Tests for the CMake/Ninja build-verification gate (feature f3523d60).

The gate adds a real ``build:``/``compile:``/``link:`` AC kind so C++/RCCL
features can no longer be rubber-stamped without compiling. These tests drive
the executor with a fake ``_run_with_pgroup_timeout`` so no real toolchain is
required.

AC: pytest: tests/test_build_verification.py
"""

from __future__ import annotations

import pathlib

import pytest

import bob.build_verification as bv
from bob.build_verification import (
    BuildResult,
    ROCM_CXX_COMPILERS,
    VALID_BUILD_KINDS,
    extract_error_lines,
    is_cmake_project,
    resolve_cxx_compiler,
    run_build_criterion,
)


@pytest.fixture
def cmake_ws(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n")
    return tmp_path


def _fake_runner(stdout="", stderr="", exit_code=0, timed_out=False):
    calls = []

    def runner(cmd, cwd, timeout_s, env=None):
        calls.append({"cmd": cmd, "cwd": cwd, "timeout_s": timeout_s, "env": env})
        return stdout, stderr, exit_code, timed_out

    runner.calls = calls
    return runner


class TestIsCmakeProject:
    def test_detects_cmakelists(self, cmake_ws):
        assert is_cmake_project(cmake_ws) is True

    def test_missing_cmakelists(self, tmp_path):
        assert is_cmake_project(tmp_path) is False

    def test_accepts_str_path(self, cmake_ws):
        assert is_cmake_project(str(cmake_ws)) is True

    def test_none_raises(self):
        with pytest.raises(ValueError):
            is_cmake_project(None)

    def test_wrong_type_raises(self):
        with pytest.raises(ValueError):
            is_cmake_project(123)


class TestResolveCompiler:
    def test_prefers_explicit(self):
        which = lambda c: f"/usr/bin/{c}" if c == "myhipcc" else None
        assert resolve_cxx_compiler("myhipcc", which=which) == "/usr/bin/myhipcc"

    def test_walks_rocm_order(self):
        which = lambda c: "/opt/rocm/bin/hipcc" if c == "hipcc" else None
        assert resolve_cxx_compiler(which=which) == "/opt/rocm/bin/hipcc"

    def test_none_when_absent(self):
        assert resolve_cxx_compiler(which=lambda c: None) is None

    def test_hipcc_is_first_preference(self):
        assert ROCM_CXX_COMPILERS[0] == "hipcc"


class TestExtractErrorLines:
    def test_prefers_error_lines(self):
        out = "note: ok\nfoo.cpp:1: error: bad\nmore\n"
        lines = extract_error_lines(out)
        assert any("error: bad" in ln for ln in lines)

    def test_falls_back_to_tail(self):
        out = "line1\nline2\nline3\n"
        lines = extract_error_lines(out, limit=2)
        assert lines == ["line2", "line3"]

    def test_empty(self):
        assert extract_error_lines("") == []


class TestRunBuildCriterion:
    def test_successful_build(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "/opt/rocm/bin/hipcc")
        runner = _fake_runner(stdout="[1/1] Building\n", exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        res = run_build_criterion(cmake_ws, "", kind="build")
        assert res.passed is True
        assert res.details == ""
        # Both configure and build steps were dispatched.
        assert len(runner.calls) == 2
        assert runner.calls[0]["cmd"][0] == "cmake"
        assert "-GNinja" in runner.calls[0]["cmd"] or "Ninja" in runner.calls[0]["cmd"]

    def test_configure_flags_present(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        runner = _fake_runner(exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        run_build_criterion(cmake_ws, "", kind="build")
        conf = runner.calls[0]["cmd"]
        assert "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON" in conf
        assert "-DCMAKE_BUILD_TYPE=RelWithDebInfo" in conf
        assert any(a.startswith("-DCMAKE_CXX_COMPILER=") for a in conf)

    def test_nonzero_build_is_hard_fail(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        # configure ok (call 1), build fails (call 2)
        outputs = [("", "", 0, False), ("foo.cpp:9: error: no member named 'x'\n", "", 1, False)]

        def runner(cmd, cwd, timeout_s, env=None):
            return outputs.pop(0)

        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        res = run_build_criterion(cmake_ws, "", kind="build")
        assert res.passed is False
        assert "error: no member" in res.details
        assert res.exit_code == 1

    def test_timeout_is_fail(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        runner = _fake_runner(exit_code=-1, timed_out=True)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        res = run_build_criterion(cmake_ws, "", kind="build", timeout=5)
        assert res.passed is False
        assert "timed out" in res.details

    def test_missing_compiler_is_fail(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: None)
        res = run_build_criterion(cmake_ws, "", kind="build")
        assert res.passed is False
        assert "compiler" in res.details.lower()

    def test_non_cmake_workspace_build_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        res = run_build_criterion(tmp_path, "", kind="build")
        assert res.passed is False
        assert "cmake" in res.details.lower()

    def test_compile_single_tu(self, cmake_ws, monkeypatch):
        (cmake_ws / "foo.cpp").write_text("int main(){return 0;}\n")
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        runner = _fake_runner(exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        res = run_build_criterion(cmake_ws, "foo.cpp", kind="compile")
        assert res.passed is True
        assert len(runner.calls) == 1
        assert runner.calls[0]["cmd"][0] == "hipcc"
        assert "-c" in runner.calls[0]["cmd"]

    def test_compile_missing_source_fails(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        res = run_build_criterion(cmake_ws, "nope.cpp", kind="compile")
        assert res.passed is False
        assert "not found" in res.details.lower()

    def test_link_unresolved_symbol_fails_even_on_zero_exit(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        outputs = [("", "", 0, False), ("", "main.o: undefined reference to `foo'\n", 0, False)]

        def runner(cmd, cwd, timeout_s, env=None):
            return outputs.pop(0)

        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        res = run_build_criterion(cmake_ws, "", kind="link")
        assert res.passed is False
        assert "unresolved" in res.details.lower()

    def test_link_artifact_must_exist(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        runner = _fake_runner(exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        res = run_build_criterion(cmake_ws, "artifact=build/libfoo.so", kind="link")
        assert res.passed is False
        assert "artifact" in res.details.lower()

    def test_link_artifact_present_passes(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        (cmake_ws / "build").mkdir()
        (cmake_ws / "build" / "libfoo.so").write_text("")
        runner = _fake_runner(exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        res = run_build_criterion(cmake_ws, "artifact=build/libfoo.so", kind="link")
        assert res.passed is True

    def test_evidence_persisted(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        runner = _fake_runner(stdout="ok\n", exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        res = run_build_criterion(cmake_ws, "", kind="build")
        assert res.evidence_path is not None
        assert pathlib.Path(res.evidence_path).exists()
        text = pathlib.Path(res.evidence_path).read_text()
        assert "command:" in text and "exit_code:" in text

    def test_result_is_iterable_tuple(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        runner = _fake_runner(exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        passed, details = run_build_criterion(cmake_ws, "", kind="build")
        assert passed is True
        assert details == ""

    def test_env_forwarded(self, cmake_ws, monkeypatch):
        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        runner = _fake_runner(exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        run_build_criterion(cmake_ws, "", kind="build", env={"MYVAR": "1"})
        assert runner.calls[0]["env"]["MYVAR"] == "1"


class TestEnhancedVerificationIntegration:
    def test_module_importable(self):
        import bob.enhanced_verification  # noqa: F401

    def test_build_prefix_routed(self, cmake_ws, monkeypatch):
        import bob.enhanced_verification as ev

        monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
        runner = _fake_runner(exit_code=0)
        monkeypatch.setattr(bv, "_run_with_pgroup_timeout", runner)
        passed, details = ev._check_criterion_with_details(
            criterion="build: .",
            workspace=cmake_ws,
            is_python_project=False,
            is_cmake_project=True,
            is_opm_project=False,
        )
        assert passed is True

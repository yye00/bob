"""Tests for bob.sanitizer_clean_ac — sanitizer-clean execution AC.

Feature 1424c7e9-f248-4beb-b49d-2e407b609328.

Covers: parsing, env construction, report scanning, instrumentation proof,
tripwire self-test, and the top-level verify_sanitizer_clean flow. All external
compile/run steps are injected via runner/prober callables so the tests are
hermetic (no compiler or sanitizer runtime required).
"""

from __future__ import annotations

import pytest

from bob.sanitizer_clean_ac import (
    SANITIZER_ENV,
    SUPPORTED_SANITIZERS,
    build_sanitizer_env,
    parse_sanitizer_clean_ac,
    run_tripwire,
    scan_sanitizer_report,
    verify_instrumentation_present,
    verify_sanitizer_clean,
)


# --------------------------------------------------------------------------- #
# Fake runner helpers
# --------------------------------------------------------------------------- #
class _Result:
    def __init__(self, returncode=0, output="", binary=None):
        self.returncode = returncode
        self.output = output
        self.binary = binary


def _caught_tripwire(sanitizer, workspace, env):
    # Non-zero exit + sanitizer report => correctly caught.
    return _Result(returncode=1, output="ERROR: AddressSanitizer: heap-buffer-overflow")


def _clean_target(sanitizer_prefix="", binary="/tmp/app"):
    def runner(command, workspace, env):
        return _Result(returncode=0, output="all tests passed", binary=binary)

    return runner


def _asan_prober(binary):
    return "0000 T __asan_init\nlibclang_rt.asan-x86_64.so"


# --------------------------------------------------------------------------- #
# parse_sanitizer_clean_ac
# --------------------------------------------------------------------------- #
class TestParse:
    def test_parses_asan_with_command(self):
        assert parse_sanitizer_clean_ac(
            "sanitizer-clean: asan ctest -R rccl_smoke"
        ) == ("asan", "ctest -R rccl_smoke")

    def test_parses_ubsan(self):
        assert parse_sanitizer_clean_ac("sanitizer-clean: ubsan ./run.sh") == (
            "ubsan",
            "./run.sh",
        )

    def test_parses_tsan(self):
        assert parse_sanitizer_clean_ac("sanitizer-clean: tsan ctest -R race") == (
            "tsan",
            "ctest -R race",
        )

    def test_case_insensitive_key_and_sanitizer(self):
        assert parse_sanitizer_clean_ac("Sanitizer-Clean: ASAN ctest") == (
            "asan",
            "ctest",
        )

    def test_extra_whitespace_tolerated(self):
        assert parse_sanitizer_clean_ac(
            "  sanitizer-clean:   asan    ctest -R foo  "
        ) == ("asan", "ctest -R foo")

    def test_non_matching_line_returns_none(self):
        assert parse_sanitizer_clean_ac("File exists: src/foo.py") is None

    def test_pytest_ac_returns_none(self):
        assert parse_sanitizer_clean_ac("pytest: tests/test_x.py") is None

    def test_unsupported_sanitizer_raises(self):
        with pytest.raises(ValueError):
            parse_sanitizer_clean_ac("sanitizer-clean: msan ctest")

    def test_missing_command_raises(self):
        with pytest.raises(ValueError):
            parse_sanitizer_clean_ac("sanitizer-clean: asan")

    def test_empty_body_raises(self):
        with pytest.raises(ValueError):
            parse_sanitizer_clean_ac("sanitizer-clean:")

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            parse_sanitizer_clean_ac(123)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# build_sanitizer_env
# --------------------------------------------------------------------------- #
class TestEnv:
    def test_asan_env_forces_exitcode_and_halt(self):
        env = build_sanitizer_env("asan")
        assert "exitcode=1" in env["ASAN_OPTIONS"]
        assert "halt_on_error=1" in env["ASAN_OPTIONS"]
        assert "detect_leaks=1" in env["ASAN_OPTIONS"]

    def test_ubsan_env_forces_exitcode(self):
        env = build_sanitizer_env("ubsan")
        assert "exitcode=1" in env["UBSAN_OPTIONS"]

    def test_tsan_env(self):
        env = build_sanitizer_env("tsan")
        assert "exitcode=1" in env["TSAN_OPTIONS"]

    def test_merges_base_env(self):
        env = build_sanitizer_env("asan", {"PATH": "/usr/bin"})
        assert env["PATH"] == "/usr/bin"
        assert "ASAN_OPTIONS" in env

    def test_all_supported_have_env(self):
        for name in SUPPORTED_SANITIZERS:
            assert name in SANITIZER_ENV

    def test_bad_base_env_raises(self):
        with pytest.raises(ValueError):
            build_sanitizer_env("asan", ["not", "a", "dict"])  # type: ignore[arg-type]

    def test_unsupported_raises(self):
        with pytest.raises(ValueError):
            build_sanitizer_env("nope")


# --------------------------------------------------------------------------- #
# scan_sanitizer_report
# --------------------------------------------------------------------------- #
class TestScanReport:
    def test_empty_is_clean(self):
        assert scan_sanitizer_report("") is True

    def test_none_is_clean(self):
        assert scan_sanitizer_report(None) is True

    def test_normal_output_is_clean(self):
        assert scan_sanitizer_report("100% tests passed") is True

    def test_asan_error_is_dirty(self):
        assert scan_sanitizer_report(
            "==1234==ERROR: AddressSanitizer: heap-buffer-overflow"
        ) is False

    def test_ubsan_runtime_error_is_dirty(self):
        assert scan_sanitizer_report("foo.cpp:5:7: runtime error: overflow") is False

    def test_leak_is_dirty(self):
        assert scan_sanitizer_report("detected memory leaks") is False

    def test_tsan_data_race_is_dirty(self):
        assert scan_sanitizer_report("WARNING: ThreadSanitizer: data race") is False


# --------------------------------------------------------------------------- #
# verify_instrumentation_present
# --------------------------------------------------------------------------- #
class TestInstrumentation:
    def test_asan_runtime_symbol_detected(self):
        assert verify_instrumentation_present(
            "/tmp/app", "asan", prober=_asan_prober
        ) is True

    def test_missing_runtime_fails(self):
        assert verify_instrumentation_present(
            "/tmp/app", "asan", prober=lambda b: "0000 T main"
        ) is False

    def test_empty_probe_fails(self):
        assert verify_instrumentation_present(
            "/tmp/app", "asan", prober=lambda b: ""
        ) is False

    def test_ubsan_detected(self):
        assert verify_instrumentation_present(
            "/tmp/app", "ubsan", prober=lambda b: "U __ubsan_handle_add_overflow"
        ) is True

    def test_empty_binary_raises(self):
        with pytest.raises(ValueError):
            verify_instrumentation_present("", "asan", prober=_asan_prober)

    def test_unsupported_raises(self):
        with pytest.raises(ValueError):
            verify_instrumentation_present("/tmp/app", "msan", prober=_asan_prober)


# --------------------------------------------------------------------------- #
# run_tripwire
# --------------------------------------------------------------------------- #
class TestTripwire:
    def test_caught_tripwire_passes(self):
        ok, reason = run_tripwire("asan", "/ws", runner=_caught_tripwire)
        assert ok is True
        assert reason == ""

    def test_always_green_harness_detected(self):
        # Tripwire exits 0 => harness is mis-wired.
        ok, reason = run_tripwire(
            "asan", "/ws", runner=lambda s, w, e: _Result(returncode=0, output="")
        )
        assert ok is False
        assert "mis-wired" in reason

    def test_nonzero_but_no_report_fails(self):
        ok, reason = run_tripwire(
            "asan", "/ws", runner=lambda s, w, e: _Result(returncode=1, output="crash")
        )
        assert ok is False
        assert "no sanitizer report" in reason

    def test_runner_exception_reported(self):
        def boom(s, w, e):
            raise RuntimeError("compiler exploded")

        ok, reason = run_tripwire("asan", "/ws", runner=boom)
        assert ok is False
        assert "compiler exploded" in reason

    def test_empty_workspace_raises(self):
        with pytest.raises(ValueError):
            run_tripwire("asan", "", runner=_caught_tripwire)

    def test_unsupported_raises(self):
        with pytest.raises(ValueError):
            run_tripwire("msan", "/ws", runner=_caught_tripwire)


# --------------------------------------------------------------------------- #
# verify_sanitizer_clean — top-level flow
# --------------------------------------------------------------------------- #
class TestVerify:
    def test_clean_run_passes(self):
        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest -R rccl",
            "/ws",
            runner=_clean_target(),
            prober=_asan_prober,
            tripwire_runner=_caught_tripwire,
        )
        assert ok is True
        assert reason == ""

    def test_dirty_report_fails(self):
        def dirty(command, workspace, env):
            return _Result(
                returncode=1,
                output="ERROR: AddressSanitizer: heap-buffer-overflow",
                binary="/tmp/app",
            )

        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest",
            "/ws",
            runner=dirty,
            prober=_asan_prober,
            tripwire_runner=_caught_tripwire,
        )
        assert ok is False
        assert "exited 1" in reason or "report" in reason

    def test_missing_instrumentation_fails(self):
        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest",
            "/ws",
            runner=_clean_target(binary="/tmp/app"),
            prober=lambda b: "0000 T main",  # no asan runtime
            tripwire_runner=_caught_tripwire,
        )
        assert ok is False
        assert "instrumentation not present" in reason

    def test_tripwire_failure_blocks(self):
        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest",
            "/ws",
            runner=_clean_target(),
            prober=_asan_prober,
            tripwire_runner=lambda s, w, e: _Result(returncode=0, output=""),
        )
        assert ok is False
        assert "tripwire self-test failed" in reason

    def test_skip_tripwire_when_already_run(self):
        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest",
            "/ws",
            runner=_clean_target(),
            prober=_asan_prober,
            skip_tripwire=True,
        )
        assert ok is True

    def test_nonzero_exit_fails(self):
        def crash(command, workspace, env):
            return _Result(returncode=134, output="", binary="/tmp/app")

        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest",
            "/ws",
            runner=crash,
            prober=_asan_prober,
            tripwire_runner=_caught_tripwire,
        )
        assert ok is False
        assert "exited 134" in reason

    def test_no_binary_skips_instrumentation_check(self):
        # A runner that reports no binary path still passes on clean exit.
        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest",
            "/ws",
            runner=lambda c, w, e: _Result(returncode=0, output="ok"),
            tripwire_runner=_caught_tripwire,
            skip_tripwire=True,
        )
        assert ok is True

    def test_dict_result_supported(self):
        def dict_runner(command, workspace, env):
            return {"returncode": 0, "output": "ok", "binary": "/tmp/app"}

        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest",
            "/ws",
            runner=dict_runner,
            prober=_asan_prober,
            skip_tripwire=True,
        )
        assert ok is True

    def test_non_sanitizer_ac_raises(self):
        with pytest.raises(ValueError):
            verify_sanitizer_clean("File exists: src/foo.py", "/ws")

    def test_empty_workspace_raises(self):
        with pytest.raises(ValueError):
            verify_sanitizer_clean("sanitizer-clean: asan ctest", "")

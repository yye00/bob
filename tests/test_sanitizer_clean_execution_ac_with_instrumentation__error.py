"""Error-path tests for bob.sanitizer_clean_ac.

Feature 1424c7e9-f248-4beb-b49d-2e407b609328.

Verifies that invalid input raises ValueError and the functions do not silently
succeed (the error path).
"""

from __future__ import annotations

import pytest

from bob.sanitizer_clean_ac import (
    build_sanitizer_env,
    parse_sanitizer_clean_ac,
    run_tripwire,
    scan_sanitizer_report,
    verify_instrumentation_present,
    verify_sanitizer_clean,
)


class TestParseErrors:
    def test_non_string_criterion_raises(self):
        with pytest.raises(ValueError):
            parse_sanitizer_clean_ac(None)  # type: ignore[arg-type]

    def test_unsupported_sanitizer_raises(self):
        with pytest.raises(ValueError):
            parse_sanitizer_clean_ac("sanitizer-clean: leaksan ctest")

    def test_missing_command_raises(self):
        with pytest.raises(ValueError):
            parse_sanitizer_clean_ac("sanitizer-clean: tsan")

    def test_empty_body_raises(self):
        with pytest.raises(ValueError):
            parse_sanitizer_clean_ac("sanitizer-clean:   ")


class TestEnvErrors:
    def test_unsupported_sanitizer_raises(self):
        with pytest.raises(ValueError):
            build_sanitizer_env("valgrind")

    def test_non_dict_base_env_raises(self):
        with pytest.raises(ValueError):
            build_sanitizer_env("asan", "PATH=/usr/bin")  # type: ignore[arg-type]

    def test_non_string_sanitizer_raises(self):
        with pytest.raises(ValueError):
            build_sanitizer_env(42)  # type: ignore[arg-type]


class TestScanErrors:
    def test_non_string_output_raises(self):
        with pytest.raises(ValueError):
            scan_sanitizer_report(["not", "a", "string"])  # type: ignore[arg-type]


class TestInstrumentationErrors:
    def test_empty_binary_raises(self):
        with pytest.raises(ValueError):
            verify_instrumentation_present("", "asan", prober=lambda b: "x")

    def test_unsupported_sanitizer_raises(self):
        with pytest.raises(ValueError):
            verify_instrumentation_present("/tmp/app", "msan", prober=lambda b: "x")


class TestTripwireErrors:
    def test_empty_workspace_raises(self):
        with pytest.raises(ValueError):
            run_tripwire("asan", "", runner=lambda s, w, e: None)

    def test_unsupported_sanitizer_raises(self):
        with pytest.raises(ValueError):
            run_tripwire("dfsan", "/ws", runner=lambda s, w, e: None)


class TestVerifyErrors:
    def test_non_sanitizer_ac_raises(self):
        with pytest.raises(ValueError):
            verify_sanitizer_clean("pytest: tests/test_x.py", "/ws")

    def test_empty_workspace_raises(self):
        with pytest.raises(ValueError):
            verify_sanitizer_clean("sanitizer-clean: asan ctest", "")

    def test_malformed_ac_raises(self):
        with pytest.raises(ValueError):
            verify_sanitizer_clean("sanitizer-clean: badsan ctest", "/ws")

    def test_does_not_silently_succeed_on_dirty(self):
        # A dirty run must return (False, reason), never a silent True.
        ok, reason = verify_sanitizer_clean(
            "sanitizer-clean: asan ctest",
            "/ws",
            runner=lambda c, w, e: {
                "returncode": 1,
                "output": "ERROR: AddressSanitizer: heap-buffer-overflow",
                "binary": "/tmp/app",
            },
            prober=lambda b: "__asan_init",
            skip_tripwire=True,
        )
        assert ok is False
        assert reason

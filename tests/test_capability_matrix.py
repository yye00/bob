"""Tests for tools/capability_matrix.py — probe bob_N capabilities."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


class TestCapabilityMatrixCLI:
    """Tests that the CLI can be invoked and produces valid JSON output."""

    def test_module_runnable_as_cli(self, tmp_path):
        out_path = tmp_path / "cm.json"
        result = subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"CLI failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

    def test_cli_creates_output_file(self, tmp_path):
        out_path = tmp_path / "cm.json"
        subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        assert out_path.exists(), "Expected output JSON file to be created"

    def test_cli_output_is_valid_json(self, tmp_path):
        out_path = tmp_path / "cm.json"
        subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        with open(out_path) as f:
            matrix = json.load(f)
        assert isinstance(matrix, dict)


class TestCapabilityMatrixStructure:
    """Tests that the output JSON has the expected top-level structure."""

    @pytest.fixture(scope="class")
    def matrix(self, tmp_path_factory):
        out_path = tmp_path_factory.mktemp("cm") / "cm.json"
        subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        with open(out_path) as f:
            return json.load(f)

    def test_has_languages_key(self, matrix):
        assert "languages" in matrix, f"Expected 'languages' key in matrix. Got: {list(matrix.keys())}"

    def test_has_test_frameworks_key(self, matrix):
        assert "test_frameworks" in matrix

    def test_has_build_systems_key(self, matrix):
        assert "build_systems" in matrix

    def test_has_gpu_verification_key(self, matrix):
        assert "gpu_verification" in matrix

    def test_has_verification_checks_key(self, matrix):
        assert "verification_checks" in matrix


class TestLanguagesSection:
    """Tests that 'languages' section has correct structure and python support."""

    @pytest.fixture(scope="class")
    def languages(self, tmp_path_factory):
        out_path = tmp_path_factory.mktemp("lang") / "cm.json"
        subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        with open(out_path) as f:
            matrix = json.load(f)
        return matrix["languages"]

    def test_python_is_present(self, languages):
        assert "python" in languages

    def test_python_supported_is_true(self, languages):
        assert languages["python"]["supported"] is True

    def test_python_has_smoke_test_passes(self, languages):
        assert "smoke_test_passes" in languages["python"]

    def test_python_has_sample_project(self, languages):
        assert "sample_project" in languages["python"]

    def test_python_smoke_test_passes_is_bool(self, languages):
        assert isinstance(languages["python"]["smoke_test_passes"], bool)

    def test_known_languages_present(self, languages):
        # At minimum these languages should be probed
        expected = {"python", "js", "ts"}
        present = set(languages.keys())
        missing = expected - present
        assert not missing, f"Missing language entries: {missing}"

    def test_each_language_has_required_fields(self, languages):
        required = {"supported", "smoke_test_passes", "sample_project"}
        for lang, info in languages.items():
            missing = required - set(info.keys())
            assert not missing, f"Language '{lang}' missing fields: {missing}"

    def test_supported_field_is_bool(self, languages):
        for lang, info in languages.items():
            assert isinstance(info["supported"], bool), (
                f"Language '{lang}' supported field must be bool, got {type(info['supported'])}"
            )


class TestTestFrameworksSection:
    """Tests the test_frameworks section."""

    @pytest.fixture(scope="class")
    def test_frameworks(self, tmp_path_factory):
        out_path = tmp_path_factory.mktemp("tf") / "cm.json"
        subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        with open(out_path) as f:
            matrix = json.load(f)
        return matrix["test_frameworks"]

    def test_pytest_is_present(self, test_frameworks):
        assert "pytest" in test_frameworks

    def test_pytest_supported_is_true(self, test_frameworks):
        assert test_frameworks["pytest"]["supported"] is True

    def test_known_frameworks_present(self, test_frameworks):
        expected = {"pytest", "jest"}
        present = set(test_frameworks.keys())
        missing = expected - present
        assert not missing, f"Missing test framework entries: {missing}"

    def test_each_framework_has_required_fields(self, test_frameworks):
        required = {"supported", "smoke_test_passes", "sample_project"}
        for fw, info in test_frameworks.items():
            missing = required - set(info.keys())
            assert not missing, f"Framework '{fw}' missing fields: {missing}"


class TestBuildSystemsSection:
    """Tests the build_systems section."""

    @pytest.fixture(scope="class")
    def build_systems(self, tmp_path_factory):
        out_path = tmp_path_factory.mktemp("bs") / "cm.json"
        subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        with open(out_path) as f:
            matrix = json.load(f)
        return matrix["build_systems"]

    def test_pip_is_present(self, build_systems):
        assert "pip" in build_systems

    def test_pip_supported_is_true(self, build_systems):
        assert build_systems["pip"]["supported"] is True

    def test_known_build_systems_present(self, build_systems):
        expected = {"pip", "npm"}
        present = set(build_systems.keys())
        missing = expected - present
        assert not missing, f"Missing build system entries: {missing}"

    def test_each_build_system_has_required_fields(self, build_systems):
        required = {"supported", "smoke_test_passes", "sample_project"}
        for bs, info in build_systems.items():
            missing = required - set(info.keys())
            assert not missing, f"Build system '{bs}' missing fields: {missing}"


class TestGPUVerificationSection:
    """Tests the gpu_verification section."""

    @pytest.fixture(scope="class")
    def gpu_verification(self, tmp_path_factory):
        out_path = tmp_path_factory.mktemp("gpu") / "cm.json"
        subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        with open(out_path) as f:
            matrix = json.load(f)
        return matrix["gpu_verification"]

    def test_compute_sanitizer_present(self, gpu_verification):
        assert "compute-sanitizer" in gpu_verification

    def test_rocprof_present(self, gpu_verification):
        assert "rocprof" in gpu_verification

    def test_each_entry_has_required_fields(self, gpu_verification):
        required = {"supported", "smoke_test_passes", "sample_project"}
        for tool, info in gpu_verification.items():
            missing = required - set(info.keys())
            assert not missing, f"GPU tool '{tool}' missing fields: {missing}"


class TestVerificationChecksSection:
    """Tests the verification_checks section lists checks from superpowers.py."""

    @pytest.fixture(scope="class")
    def verification_checks(self, tmp_path_factory):
        out_path = tmp_path_factory.mktemp("vc") / "cm.json"
        subprocess.run(
            [sys.executable, "-m", "tools.capability_matrix", "--out", str(out_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        with open(out_path) as f:
            matrix = json.load(f)
        return matrix["verification_checks"]

    def test_is_list(self, verification_checks):
        assert isinstance(verification_checks, list)

    def test_has_items(self, verification_checks):
        assert len(verification_checks) > 0

    def test_contains_tests_pass(self, verification_checks):
        assert "tests_pass" in verification_checks

    def test_contains_source_files_exist(self, verification_checks):
        assert "source_files_exist" in verification_checks


class TestHistoryFile:
    """Tests that the history JSONL file is written."""

    def test_history_file_written(self, tmp_path):
        out_path = tmp_path / "cm.json"
        history_path = tmp_path / "history.jsonl"
        result = subprocess.run(
            [
                sys.executable, "-m", "tools.capability_matrix",
                "--out", str(out_path),
                "--history", str(history_path),
            ],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert history_path.exists(), "History JSONL file should be created"

    def test_history_file_is_valid_jsonl(self, tmp_path):
        out_path = tmp_path / "cm.json"
        history_path = tmp_path / "history.jsonl"
        subprocess.run(
            [
                sys.executable, "-m", "tools.capability_matrix",
                "--out", str(out_path),
                "--history", str(history_path),
            ],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        lines = history_path.read_text().strip().splitlines()
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert "timestamp" in entry
        assert "matrix" in entry


class TestImportableModule:
    """Tests that the module can be imported and has expected interface."""

    def test_module_importable(self):
        import importlib
        mod = importlib.import_module("tools.capability_matrix")
        assert mod is not None

    def test_probe_function_exists(self):
        import importlib
        mod = importlib.import_module("tools.capability_matrix")
        assert hasattr(mod, "probe_capabilities"), "Expected probe_capabilities() function"

    def test_probe_returns_dict(self):
        import importlib
        mod = importlib.import_module("tools.capability_matrix")
        result = mod.probe_capabilities()
        assert isinstance(result, dict)

    def test_probe_languages_python_supported(self):
        import importlib
        mod = importlib.import_module("tools.capability_matrix")
        result = mod.probe_capabilities()
        assert result["languages"]["python"]["supported"] is True


def test_capability_matrix_languages_python():
    """Module-level test: python must be supported with supported=True."""
    import importlib
    mod = importlib.import_module("tools.capability_matrix")
    result = mod.probe_capabilities()
    assert "languages" in result
    assert "python" in result["languages"]
    assert result["languages"]["python"]["supported"] is True

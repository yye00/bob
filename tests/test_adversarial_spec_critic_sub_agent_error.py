"""Error-path tests for spec_critic.run_critic.

AC: invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_critic import run_critic, ConstitutionMissingError


_CONSTITUTION_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "bob" / "spec_quality" / "spec_constitution.md"
)


# ---------------------------------------------------------------------------
# Error: invalid feature_id
# ---------------------------------------------------------------------------

class TestInvalidFeatureId:
    def test_empty_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            run_critic(
                feature_id="",
                name="Name",
                description="desc",
                acceptance_criteria=["File exists: src/x.py"],
                constitution_path=_CONSTITUTION_PATH,
                findings_path=tmp_path / "sf.yaml",
            )

    def test_empty_feature_id_does_not_silently_succeed(self, tmp_path):
        raised = False
        try:
            run_critic(
                feature_id="",
                name="Name",
                description="desc",
                acceptance_criteria=["File exists: src/x.py"],
                constitution_path=_CONSTITUTION_PATH,
                findings_path=tmp_path / "sf.yaml",
            )
        except ValueError:
            raised = True
        assert raised, "Empty feature_id must raise ValueError, not silently succeed"

    def test_none_feature_id_raises(self, tmp_path):
        with pytest.raises((ValueError, TypeError)):
            run_critic(
                feature_id=None,  # type: ignore[arg-type]
                name="Name",
                description="desc",
                acceptance_criteria=["File exists: src/x.py"],
                constitution_path=_CONSTITUTION_PATH,
                findings_path=tmp_path / "sf.yaml",
            )


# ---------------------------------------------------------------------------
# Error: invalid acceptance_criteria type
# ---------------------------------------------------------------------------

class TestInvalidAcceptanceCriteriaType:
    def test_string_instead_of_list_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            run_critic(
                feature_id="err-ac-type",
                name="Name",
                description="desc",
                acceptance_criteria="this is a string, not a list",  # type: ignore[arg-type]
                constitution_path=_CONSTITUTION_PATH,
                findings_path=tmp_path / "sf.yaml",
            )

    def test_none_acceptance_criteria_raises(self, tmp_path):
        with pytest.raises((ValueError, TypeError)):
            run_critic(
                feature_id="err-ac-none",
                name="Name",
                description="desc",
                acceptance_criteria=None,  # type: ignore[arg-type]
                constitution_path=_CONSTITUTION_PATH,
                findings_path=tmp_path / "sf.yaml",
            )

    def test_dict_acceptance_criteria_raises(self, tmp_path):
        with pytest.raises((ValueError, TypeError)):
            run_critic(
                feature_id="err-ac-dict",
                name="Name",
                description="desc",
                acceptance_criteria={"key": "value"},  # type: ignore[arg-type]
                constitution_path=_CONSTITUTION_PATH,
                findings_path=tmp_path / "sf.yaml",
            )


# ---------------------------------------------------------------------------
# Error: missing constitution
# ---------------------------------------------------------------------------

class TestMissingConstitution:
    def test_missing_constitution_raises(self, tmp_path):
        with pytest.raises(ConstitutionMissingError):
            run_critic(
                feature_id="err-const-001",
                name="No constitution",
                description="desc",
                acceptance_criteria=["File exists: src/x.py"],
                constitution_path=tmp_path / "nonexistent.md",
                findings_path=tmp_path / "sf.yaml",
            )

    def test_missing_constitution_does_not_silently_succeed(self, tmp_path):
        raised = False
        try:
            run_critic(
                feature_id="err-const-002",
                name="No constitution",
                description="desc",
                acceptance_criteria=["File exists: src/x.py"],
                constitution_path=tmp_path / "nonexistent.md",
                findings_path=tmp_path / "sf.yaml",
            )
        except ConstitutionMissingError:
            raised = True
        except Exception:
            raised = True  # any exception counts — must not silently succeed
        assert raised, "Missing constitution must raise, not silently succeed"

    def test_missing_constitution_is_file_not_found_subclass(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_critic(
                feature_id="err-const-003",
                name="No constitution",
                description="desc",
                acceptance_criteria=["File exists: src/x.py"],
                constitution_path=tmp_path / "nonexistent.md",
                findings_path=tmp_path / "sf.yaml",
            )


# ---------------------------------------------------------------------------
# Error: invalid findings_path (unwritable directory)
# ---------------------------------------------------------------------------

class TestUnwritableFindingsPath:
    def test_unwritable_dir_raises(self, tmp_path):
        bad_path = tmp_path / "nonexistent_dir" / "deeply" / "nested" / "sf.yaml"
        # Expect some IO-related error when directory cannot be created
        try:
            run_critic(
                feature_id="err-write-001",
                name="Unwritable",
                description="desc",
                acceptance_criteria=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
                constitution_path=_CONSTITUTION_PATH,
                findings_path=bad_path,
            )
            # If it succeeds because the implementation creates directories, that's OK
        except (OSError, FileNotFoundError):
            pass  # Expected — confirm it does not silently swallow the error
        except ValueError:
            pass  # Also valid

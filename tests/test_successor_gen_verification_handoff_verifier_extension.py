"""Tests for bob.successor_gen_verification_handoff_verifier_extension (88d90cdc).

Acceptance criteria:
- File exists: src/bob/successor_gen_verification_handoff_verifier_extension.py
- Function defined: bob.successor_gen_verification_handoff_verifier_extension.successor_gen_verification_handoff_verifier_extension
- pytest: tests/test_successor_gen_verification_handoff_verifier_extension.py::test_successor_gen_verification_handoff_verifier_extension
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# AC 1: File exists — src/bob/successor_gen_verification_handoff_verifier_extension.py
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_module_file_exists(self):
        import bob.successor_gen_verification_handoff_verifier_extension as m

        module_file = Path(m.__file__)
        assert module_file.exists()
        assert module_file.name == "successor_gen_verification_handoff_verifier_extension.py"

    def test_module_importable(self):
        import bob.successor_gen_verification_handoff_verifier_extension  # noqa: F401

    def test_expected_names_exported(self):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            PENDING_SUCCESSOR_VERIFY_STATUS,
            VERIFIER_EXTENSION_MODULES,
            successor_gen_verification_handoff_verifier_extension,
        )
        assert callable(successor_gen_verification_handoff_verifier_extension)
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert PENDING_SUCCESSOR_VERIFY_STATUS == "pending_successor_verify"

    def test_all_contains_expected_names(self):
        from bob.successor_gen_verification_handoff_verifier_extension import __all__
        assert "successor_gen_verification_handoff_verifier_extension" in __all__
        assert "PENDING_SUCCESSOR_VERIFY_STATUS" in __all__
        assert "VERIFIER_EXTENSION_MODULES" in __all__


# ---------------------------------------------------------------------------
# AC 2: Function defined
# ---------------------------------------------------------------------------


class TestFunctionDefined:
    def test_function_is_callable(self):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        assert callable(successor_gen_verification_handoff_verifier_extension)

    def test_function_signature_has_required_params(self):
        import inspect
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        sig = inspect.signature(successor_gen_verification_handoff_verifier_extension)
        params = list(sig.parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params

    def test_function_returns_bool(self, tmp_path):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        with patch(
            "bob.successor_gen_verification_handoff_verifier_extension.set_pending_successor_verify",
            return_value=False,
        ):
            result = successor_gen_verification_handoff_verifier_extension(
                "feat-001", None, False
            )
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# AC 3: pytest test function — main integration test
# ---------------------------------------------------------------------------


def test_successor_gen_verification_handoff_verifier_extension(tmp_path):
    """Main pytest AC test: verify the handoff function works end-to-end.

    Creates a workspace that contains enhanced_verification.py (a verifier-extension
    module), then calls the handoff function with structural_ac_passed=True and
    confirms it returns True and updates the DB.
    """
    from bob.successor_gen_verification_handoff_verifier_extension import (
        successor_gen_verification_handoff_verifier_extension,
    )

    # Set up a workspace with a verifier-extension module present
    src_bob = tmp_path / "src" / "bob"
    src_bob.mkdir(parents=True)
    (src_bob / "enhanced_verification.py").write_text("# patched verifier")

    # Patch the DB layer to avoid real DB writes in the test
    with patch("bob.pending_successor_verify.db") as mock_db:
        result = successor_gen_verification_handoff_verifier_extension(
            feature_id="88d90cdc-39f9-453c-8840-53722dfdad1a",
            workspace=tmp_path,
            structural_ac_passed=True,
        )

    assert result is True
    mock_db.update_feature.assert_called_once_with(
        "88d90cdc-39f9-453c-8840-53722dfdad1a",
        status="pending_successor_verify",
    )


# ---------------------------------------------------------------------------
# Guard conditions
# ---------------------------------------------------------------------------


class TestGuardConditions:
    def test_returns_false_when_structural_ac_not_passed(self, tmp_path):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch(
            "bob.successor_gen_verification_handoff_verifier_extension.set_pending_successor_verify"
        ) as mock_set:
            result = successor_gen_verification_handoff_verifier_extension(
                "feat-001", tmp_path, structural_ac_passed=False
            )
        assert result is False
        mock_set.assert_not_called()

    def test_returns_false_when_not_verifier_extension(self, tmp_path):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "regular_module.py").write_text("# not a verifier")

        with patch(
            "bob.successor_gen_verification_handoff_verifier_extension.set_pending_successor_verify"
        ) as mock_set:
            result = successor_gen_verification_handoff_verifier_extension(
                "feat-001", tmp_path, structural_ac_passed=True
            )
        assert result is False
        mock_set.assert_not_called()

    def test_returns_false_when_workspace_is_none(self):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        with patch(
            "bob.successor_gen_verification_handoff_verifier_extension.set_pending_successor_verify"
        ) as mock_set:
            result = successor_gen_verification_handoff_verifier_extension(
                "feat-001", None, structural_ac_passed=True
            )
        assert result is False
        mock_set.assert_not_called()

    def test_returns_false_when_both_conditions_fail(self):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        with patch(
            "bob.successor_gen_verification_handoff_verifier_extension.set_pending_successor_verify"
        ) as mock_set:
            result = successor_gen_verification_handoff_verifier_extension(
                "feat-001", None, structural_ac_passed=False
            )
        assert result is False
        mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_delegates_to_set_pending_successor_verify(self, tmp_path):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch(
            "bob.successor_gen_verification_handoff_verifier_extension.set_pending_successor_verify",
            return_value=True,
        ) as mock_set:
            result = successor_gen_verification_handoff_verifier_extension(
                "feat-xyz", tmp_path, structural_ac_passed=True
            )
        assert result is True
        mock_set.assert_called_once_with("feat-xyz", tmp_path, True)

    def test_works_for_verification_submodule(self, tmp_path):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        verif_dir = tmp_path / "src" / "bob" / "verification"
        verif_dir.mkdir(parents=True)
        (verif_dir / "verifier.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = successor_gen_verification_handoff_verifier_extension(
                "feat-sub", tmp_path, structural_ac_passed=True
            )
        assert result is True

    def test_logs_info_on_deferral(self, tmp_path, caplog):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db"):
            with caplog.at_level(
                logging.INFO,
                logger="bob.successor_gen_verification_handoff_verifier_extension",
            ):
                successor_gen_verification_handoff_verifier_extension(
                    "feat-log", tmp_path, structural_ac_passed=True
                )
        assert any("deferred to successor-gen" in r.message for r in caplog.records)

    def test_returns_false_when_set_pending_returns_false(self, tmp_path):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch(
            "bob.successor_gen_verification_handoff_verifier_extension.set_pending_successor_verify",
            return_value=False,
        ):
            result = successor_gen_verification_handoff_verifier_extension(
                "feat-fail", tmp_path, structural_ac_passed=True
            )
        assert result is False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestLogging:
    def test_logs_debug_when_no_structural_ac(self, tmp_path, caplog):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        with caplog.at_level(
            logging.DEBUG,
            logger="bob.successor_gen_verification_handoff_verifier_extension",
        ):
            successor_gen_verification_handoff_verifier_extension(
                "feat-d1", tmp_path, structural_ac_passed=False
            )
        assert any("no structural AC passed" in r.message for r in caplog.records)

    def test_logs_debug_when_not_verifier_extension(self, tmp_path, caplog):
        from bob.successor_gen_verification_handoff_verifier_extension import (
            successor_gen_verification_handoff_verifier_extension,
        )
        src = tmp_path / "src"
        src.mkdir()
        with caplog.at_level(
            logging.DEBUG,
            logger="bob.successor_gen_verification_handoff_verifier_extension",
        ):
            successor_gen_verification_handoff_verifier_extension(
                "feat-d2", tmp_path, structural_ac_passed=True
            )
        assert any("not a verifier-extension" in r.message for r in caplog.records)

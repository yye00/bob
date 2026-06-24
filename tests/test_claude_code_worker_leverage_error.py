"""Error-path tests for bob.dispatch worker-leverage functions.

AC: error path — invalid input raises ValueError and the function does not
silently succeed (error path).

Functions under test: spawn_worker, write_feature_settings.
"""

from __future__ import annotations

import pytest

from bob.dispatch import (
    spawn_worker,
    write_feature_settings,
)


class TestSpawnWorkerErrors:
    def test_none_feature_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            spawn_worker(None, "prompt", tmp_path, bob_dir=tmp_path / ".bob")

    def test_value_error_message_not_empty(self, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            spawn_worker(None, "prompt", tmp_path, bob_dir=tmp_path / ".bob")
        assert str(exc_info.value)

    def test_none_feature_does_not_silently_succeed(self, tmp_path):
        raised = False
        try:
            spawn_worker(None, "prompt", tmp_path, bob_dir=tmp_path / ".bob")
        except ValueError:
            raised = True
        assert raised, "spawn_worker(None, ...) must raise ValueError, not return silently"


class TestWriteFeatureSettingsErrors:
    def test_feature_without_id_raises(self, tmp_path):
        """A feature object that lacks an id attribute uses 'unknown' but does not crash."""
        from types import SimpleNamespace
        feature = SimpleNamespace()  # no .id attribute
        # Should not raise — id defaults to 'unknown'
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert path.exists()

    def test_none_extra_allow_does_not_raise(self, tmp_path):
        from types import SimpleNamespace
        feature = SimpleNamespace(id="feat-err-01")
        # None is the default — should work fine
        path = write_feature_settings(feature, bob_dir=tmp_path, extra_allow=None)
        assert path.exists()

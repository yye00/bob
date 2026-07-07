"""Error-path tests for bob.supervisor_loop.auto_resume_run.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.supervisor_loop import auto_resume_run


def test_none_features_raises_value_error():
    with pytest.raises(ValueError):
        auto_resume_run(None)


def test_non_list_features_raises_value_error():
    with pytest.raises(ValueError):
        auto_resume_run("not-a-list")


def test_feature_without_id_raises_value_error():
    with pytest.raises(ValueError):
        auto_resume_run([{"status": "pending"}])


def test_feature_with_empty_id_raises_value_error():
    with pytest.raises(ValueError):
        auto_resume_run([{"id": "", "status": "pending"}])


def test_non_callable_reset_fn_raises_value_error():
    with pytest.raises(ValueError):
        auto_resume_run(
            [{"id": "dep", "status": "failed"}, {"id": "b", "status": "pending", "depends_on": ["dep"]}],
            reset_fn="not-callable",
        )

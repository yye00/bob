"""Boundary tests: empty/zero/minimum input returns a well-defined result
rather than raising (feature d6497bed)."""

from __future__ import annotations

from bob.backend_required_check import BackendCheckResult, check_backend_required


COMPUTE_FEATURE = {
    "name": "GPU kernel",
    "description": "A HIP GPU kernel computing a reduction.",
    "acceptance_criteria": [],
}


def test_none_src_files_returns_result_not_raises(monkeypatch):
    monkeypatch.delenv("BOB_REQUIRE_GPU_BACKEND", raising=False)
    res = check_backend_required(COMPUTE_FEATURE, None)
    assert isinstance(res, BackendCheckResult)
    assert res.passed is True  # disabled by default


def test_empty_list_src_files_enabled_compute(monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    res = check_backend_required(COMPUTE_FEATURE, [])
    assert isinstance(res, BackendCheckResult)
    # A compute feature that wrote no source files has no backend evidence.
    assert res.passed is False
    assert res.status == "backend_missing"
    assert "wrote no source files" in res.reason


def test_empty_feature_mapping_is_not_compute(monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    res = check_backend_required({}, [])
    assert res.passed is True
    assert res.status == "exempt"
    assert res.is_compute is False


def test_empty_string_env_treated_as_disabled():
    res = check_backend_required(COMPUTE_FEATURE, [], env={"BOB_REQUIRE_GPU_BACKEND": ""})
    assert res.passed is True
    assert res.status == "disabled"


def test_omitted_src_files_defaults_to_none(monkeypatch):
    monkeypatch.delenv("BOB_REQUIRE_GPU_BACKEND", raising=False)
    res = check_backend_required(COMPUTE_FEATURE)
    assert isinstance(res, BackendCheckResult)
    assert res.passed is True

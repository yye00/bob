# bob_orchestrator package


def verdict_infra_only(feature_id, workspace=None):
    """Lazy proxy to rca_layer.infra_error_recovery.verdict_infra_only — integration ff679834."""
    from rca_layer.infra_error_recovery import verdict_infra_only as _fn  # noqa: PLC0415
    return _fn(feature_id, workspace=workspace)


def append_novel_signature(pattern, feature_id):
    """Lazy proxy to rca_layer.infra_error_recovery.append_novel_signature — integration ff679834."""
    from rca_layer.infra_error_recovery import append_novel_signature as _fn  # noqa: PLC0415
    return _fn(pattern, feature_id)

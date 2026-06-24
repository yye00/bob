"""bob3.verification.verifier — integration shim exposing ac_artifact_check and
mutation_gate APIs.

This module makes verify_ac_artifacts and related symbols available under the
bob3.verification.verifier namespace so the orchestrator can import from a
single stable location without coupling to ac_artifact_check directly.
It also re-exports the mutation gate for pipeline integration.
"""
from __future__ import annotations

from bob3.verification.ac_artifact_check import (  # noqa: F401
    ArtifactMiss,
    ArtifactMissingError,
    check_file_exists_ac,
    check_file_modified_ac,
    check_function_defined_ac,
    check_pytest_ac,
    fail_feature_with_explicit_reason,
    handle_unknown_prefix,
    recognized_ac_prefixes,
    verify_ac_artifacts,
)
from bob3.verification.per_feature_test_scope import (  # noqa: F401
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)
from bob3.verification.mutation_gate import (  # noqa: F401
    MutationReport,
    MutmutMissingError,
    default_threshold,
    enforce_time_limit,
    handle_mutmut_unavailable,
    mutation_operators,
    never_mutates_failing_impl,
    passes_gate,
    persist_surviving_mutants,
    return_feature_to_ready_on_failure,
    run_mutation_test,
    runs_only_after_pytest_pass,
)
from bob3.verification.regression_attribution import (  # noqa: F401
    attribute_regression_to_owner,
    filter_attributable_failures,
    is_attributable_to_current_feature,
    owning_feature_for_test,
)
from bob3.test_attribution import (  # noqa: F401
    attribute_failure_to_owner,
    attribute_regression_to_owning_feature,
    attribute_test_failure,
    build_test_to_feature_map,
    get_test_owning_feature,
)
def _import_charge_feature_from_test():  # noqa: F401 — lazy to break circular import
    from bob3.verification.blame_feature_charger import charge_feature_from_test
    return charge_feature_from_test


charge_feature_from_test = _import_charge_feature_from_test  # type: ignore[assignment]

__all__ = [
    "ArtifactMiss",
    "ArtifactMissingError",
    "check_file_exists_ac",
    "check_file_modified_ac",
    "check_function_defined_ac",
    "check_pytest_ac",
    "fail_feature_with_explicit_reason",
    "handle_unknown_prefix",
    "recognized_ac_prefixes",
    "verify_ac_artifacts",
    # per_feature_test_scope
    "SiblingTestCollectionError",
    "assert_no_sibling_collection",
    "build_scoped_pytest_argv",
    "collect_feature_test_paths",
    "scope_pytest_to_feature",
    # mutation_gate
    "MutationReport",
    "MutmutMissingError",
    "default_threshold",
    "enforce_time_limit",
    "handle_mutmut_unavailable",
    "mutation_operators",
    "never_mutates_failing_impl",
    "passes_gate",
    "persist_surviving_mutants",
    "return_feature_to_ready_on_failure",
    "run_mutation_test",
    "runs_only_after_pytest_pass",
    # regression_attribution
    "attribute_regression_to_owner",
    "filter_attributable_failures",
    "is_attributable_to_current_feature",
    "owning_feature_for_test",
    # test_attribution
    "attribute_failure_to_owner",
    "attribute_test_failure",
    "build_test_to_feature_map",
    "get_test_owning_feature",
    # blame feature charger
    "charge_feature_from_test",
]

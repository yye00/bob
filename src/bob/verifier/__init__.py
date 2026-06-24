"""Bob verifier sub-package."""

from bob.behavior_criteria import (  # noqa: F401
    EARSBehaviorCriterion,
    parse_behavior_criteria,
)
from bob.mutation_testing import (  # noqa: F401
    MUTATION_SCORE_THRESHOLD,
    run_mutation_tests,
)
from bob.mutation_gate import (  # noqa: F401 — mutation_gate verifier integration
    check_mutation_score,
    run_mutation_testing,
)
from bob.enhanced_verification import extract_and_verify_literals  # noqa: F401
from bob.enhanced_verification import extract_and_verify_literal_strings  # noqa: F401
from bob.enhanced_verification import extract_and_verify_substring_ac  # noqa: F401
from bob.enhanced_verification import extract_behavior_ac_literals  # noqa: F401
from bob.enhanced_verification import verify_behavior_ac_with_substring_grep  # noqa: F401
from bob.enhanced_verification import verify_quoted_substring  # noqa: F401
from bob.enhanced_verification import verify_quoted_substring_ac  # noqa: F401
from bob.behavior_ac_verifier import verify_quoted_substring_ac as _bav_verify_quoted_substring_ac  # noqa: F401
from bob.verifier.feature_test_scoper import (  # noqa: F401
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
    scope_pytest_to_feature_subtree,
)
from bob.verifier.pytest_scoping import (  # noqa: F401
    ScopedPytestResult,
    ScopedPytestSkipped,
    build_scoped_argv,
    scoped_pytest_runner,
)
from bob.verifier.shell_script_ac import handle_shell_script_ac  # noqa: F401
from bob.patterns.pattern_9_shell_handler import demote_shell_script_ac  # noqa: F401
from bob.verifier.pattern9_shell_integration import (  # noqa: F401 — F-R7-594 Pattern 9
    is_shell_script_integration,
    demote_to_pass_with_warning,
)
from bob.verifier.shell_script_ac import handle_shell_script_ac as check_shell_script_integration  # noqa: F401
from bob.verifier.shell_script_ac import handle_shell_script_ac as demote_shell_script_integration_ac  # noqa: F401
from bob.verifier.shell_script_ac import handle_shell_script_ac as pattern9_shell_script_handler  # noqa: F401 — F-R7-594 Pattern 9 canonical name
from bob_legacy.baseline_gate import CollectionResult, validate_collection  # noqa: F401
from bob.verifier.baseline_gate import (  # noqa: F401
    BaselineUnstableError,
    abort_on_collection_failure,
    should_abort_on_collection_failure,
)
from bob.baseline_gate import check_baseline_collection  # noqa: F401
from bob.baseline_gate import validate_baseline_collection  # noqa: F401
from bob.stable_baseline_gate import enforce_stable_baseline_gate  # noqa: F401
from bob.snapshot_determinism import enforce_maxfail_zero  # noqa: F401


def walk_ac_table(*args, **kwargs):  # noqa: F401 — regression cascade integration (lazy to avoid circular import)
    """Lazy proxy to bob.regression_cascade.walk_ac_table."""
    from bob.regression_cascade import walk_ac_table as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def charge_feature_by_test_ownership(*args, **kwargs):  # noqa: F401 — regression cascade integration (lazy)
    """Lazy proxy to bob.regression_cascade.charge_feature_by_test_ownership."""
    from bob.regression_cascade import charge_feature_by_test_ownership as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def RegressionCascadeOrphanTestError(*args, **kwargs):  # noqa: F401 — regression cascade OrphanTestError (lazy)
    """Lazy proxy to bob.regression_cascade.OrphanTestError."""
    from bob.regression_cascade import OrphanTestError  # noqa: PLC0415
    raise OrphanTestError(*args)
def generate_kxk_matrix(*args, **kwargs):  # noqa: F401 — codet_triangulation integration (lazy to avoid circular import)
    """Lazy proxy to bob.codet_triangulation.generate_kxk_matrix."""
    from bob.codet_triangulation import generate_kxk_matrix as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def mutual_agreement_scorer(*args, **kwargs):  # noqa: F401 — codet_triangulation integration (lazy)
    """Lazy proxy to bob.codet_triangulation.mutual_agreement_scorer."""
    from bob.codet_triangulation import mutual_agreement_scorer as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def score_kxk_matrix(*args, **kwargs):  # noqa: F401 — codet_triangulation integration (lazy)
    """Lazy proxy to bob.codet_triangulation.score_kxk_matrix."""
    from bob.codet_triangulation import score_kxk_matrix as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def spawn_candidate_implementations(*args, **kwargs):  # noqa: F401 — codet_triangulation integration (lazy)
    """Lazy proxy to bob.codet_triangulation.spawn_candidate_implementations."""
    from bob.codet_triangulation import spawn_candidate_implementations as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def spawn_candidate_tests(*args, **kwargs):  # noqa: F401 — codet_triangulation integration (lazy)
    """Lazy proxy to bob.codet_triangulation.spawn_candidate_tests."""
    from bob.codet_triangulation import spawn_candidate_tests as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)
from bob.spec_quality.example_grammar import (  # noqa: F401
    KeyExample,
    PropertyAC,
    emit_hypothesis_test,
    emit_parametrize_test,
)


def run_property_test(prop: "PropertyAC", *, seed: int = 0) -> tuple[bool, str]:
    """Emit and execute a Hypothesis test for a property-based AC.

    Generates a runnable Hypothesis ``@given``-decorated test from *prop*,
    writes it to a temporary module, and executes it with pytest.

    Args:
        prop: A :class:`~bob.spec_quality.example_grammar.PropertyAC` parsed
              from a ``property: <name> for <generator> assert <predicate>`` AC.
        seed: Hypothesis database seed for reproducibility.  Default is ``0``.

    Returns:
        A ``(passed, output)`` tuple where *passed* is ``True`` when pytest
        exits with code 0 and *output* is the captured stdout/stderr.

    Raises:
        TypeError: When *prop* is not a :class:`PropertyAC`.
        ValueError: When *prop* is ``None``.
    """
    if prop is None:
        raise ValueError("prop must not be None")
    if not isinstance(prop, PropertyAC):
        raise TypeError(
            f"prop must be a PropertyAC, got {type(prop).__name__!r}"
        )

    import subprocess
    import sys
    import tempfile
    import textwrap

    test_source = emit_hypothesis_test(prop, seed=seed)
    hypothesis_preamble = textwrap.dedent(
        """\
        from hypothesis import given, settings, seed as hypothesis_seed
        import hypothesis.strategies as st
        """
    )
    full_source = hypothesis_preamble + "\n" + test_source

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="bob_prop_test_", delete=False
    ) as f:
        f.write(full_source)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", tmp_path, "-v", "--tb=short"],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    finally:
        import os
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_key_example_test(
    examples: "list[KeyExample]",
    *,
    test_name: str = "test_key_examples",
    seed: int = 0,
) -> tuple[bool, str]:
    """Emit and execute a parametrized pytest for key-example ACs.

    Generates a ``@pytest.mark.parametrize``-decorated test from *examples*,
    writes it to a temporary module, and executes it with pytest.

    Args:
        examples: List of :class:`~bob.spec_quality.example_grammar.KeyExample`
                  objects to parametrize over.
        test_name: Name for the generated test function.  Default is
                   ``"test_key_examples"``.
        seed:      Seed value stored in the generated test comment for
                   reproducibility.  Default is ``0``.

    Returns:
        A ``(passed, output)`` tuple where *passed* is ``True`` when pytest
        exits with code 0 and *output* is the captured stdout/stderr.
        When *examples* is empty, returns ``(True, "")`` immediately.

    Raises:
        TypeError: When *examples* is not a list.
        ValueError: When *examples* is ``None``.
    """
    if examples is None:
        raise ValueError("examples must not be None")
    if not isinstance(examples, list):
        raise TypeError(
            f"examples must be a list, got {type(examples).__name__!r}"
        )

    if not examples:
        return True, ""

    import subprocess
    import sys
    import tempfile

    test_source = emit_parametrize_test(examples, test_name=test_name, seed=seed)
    if not test_source:
        return True, ""

    preamble = "import pytest\n\n"
    full_source = preamble + test_source

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="bob_key_test_", delete=False
    ) as f:
        f.write(full_source)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", tmp_path, "-v", "--tb=short"],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    finally:
        import os
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def verify_behavior_ac(ac: str) -> EARSBehaviorCriterion | None:
    """Parse and return a structured EARS behavior AC criterion.

    Uses :func:`bob.behavior_criteria.parse_behavior_criteria` to parse
    *ac* into an :class:`EARSBehaviorCriterion`. Returns ``None`` for
    non-behavior ACs. Raises :exc:`ValueError` for malformed behavior ACs.

    This is the canonical integration point in ``bob.verifier`` for the
    sixth AC grammar (EARS-style behavior criteria).

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        :class:`EARSBehaviorCriterion` on success; ``None`` for non-behavior ACs.

    Raises:
        ValueError: For malformed behavior ACs (``behavior:`` prefix present
            but ``when`` clause absent or unparseable).
    """
    return parse_behavior_criteria(ac)


__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "run_mutation_tests",
    "BaselineUnstableError",
    "abort_on_collection_failure",
    "should_abort_on_collection_failure",
    "CollectionResult",
    "SiblingTestCollectionError",
    "ScopedPytestResult",
    "ScopedPytestSkipped",
    "assert_no_sibling_collection",
    "build_scoped_argv",
    "build_scoped_pytest_argv",
    "collect_feature_test_paths",
    "check_shell_script_integration",
    "demote_shell_script_ac",
    "demote_shell_script_integration_ac",
    "handle_shell_script_ac",
    "is_shell_script_integration",
    "demote_to_pass_with_warning",
    "scope_pytest_to_feature",
    "scope_pytest_to_feature_subtree",
    "scoped_pytest_runner",
    "check_baseline_collection",
    "validate_baseline_collection",
    "validate_collection",
    "extract_and_verify_literals",
    "extract_and_verify_literal_strings",
    "extract_and_verify_substring_ac",
    "extract_behavior_ac_literals",
    "verify_behavior_ac_with_substring_grep",
    "verify_quoted_substring",
    "verify_behavior_ac",
    "verify_quoted_substring_ac",
    "EARSBehaviorCriterion",
    "parse_behavior_criteria",
    "run_property_test",
    "run_key_example_test",
    "emit_hypothesis_test",
    "emit_parametrize_test",
    "PropertyAC",
    "KeyExample",
    "enforce_maxfail_zero",
    "generate_kxk_matrix",
    "mutual_agreement_scorer",
    "score_kxk_matrix",
    "spawn_candidate_implementations",
    "spawn_candidate_tests",
    "walk_ac_table",
    "charge_feature_by_test_ownership",
    "RegressionCascadeOrphanTestError",
]

"""Acceptance criteria grammar extensions for the seventh AC form."""

from bob3.verification.ac_artifact_check import (
    ArtifactMiss,
    ArtifactMissingError,
    fail_feature_with_explicit_reason,
    recognized_ac_prefixes,
    verify_ac_artifacts,
)
from ac_grammar.property_based import (
    parse_property_ac,
    parse_key_example_ac,
)
from bob3.acceptance_criteria.property_based import PropertyBasedAC
from bob3.acceptance_criteria.key_examples import KeyExampleAC
from bob3.ears_behavior_parser import (
    EARSBehavior,
    parse_behavior_ac,
    parse_behavior_criterion,
)


def verify_artifact_existence(acs, workspace):
    """Pre-pytest artifact-existence verifier; delegates to verify_ac_artifacts.

    Raises ValueError when acs is not a list or workspace is None.
    """
    from pathlib import Path

    if not isinstance(acs, list):
        raise ValueError(
            f"acs must be a list of strings, got {type(acs).__name__!r}"
        )
    if workspace is None:
        raise ValueError("workspace must not be None")

    for i, item in enumerate(acs):
        if not isinstance(item, str):
            raise TypeError(
                f"acs[{i}] must be a str, got {type(item).__name__!r}: {item!r}"
            )

    return verify_ac_artifacts(acs, Path(workspace))


__all__ = [
    "ArtifactMiss",
    "ArtifactMissingError",
    "EARSBehavior",
    "KeyExampleAC",
    "PropertyBasedAC",
    "fail_feature_with_explicit_reason",
    "parse_behavior_ac",
    "parse_behavior_criterion",
    "parse_key_example_ac",
    "parse_property_ac",
    "recognized_ac_prefixes",
    "verify_artifact_existence",
]

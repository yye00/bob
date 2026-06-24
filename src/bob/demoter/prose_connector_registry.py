"""Prose connector registry for AC demotion — bob demoter package.

Exposes get_prose_connectors as the canonical public surface for the
frozenset of tokens that signal descriptive/policy prose in integration-AC
bodies and prose-AC demotion.

This is the single source of truth. Both the prose-AC demoter and the
integration-AC resolver MUST consume this registry rather than defining
their own connector lists.
"""
from __future__ import annotations

from bob.verification.structural_prefix_match import prose_connector_registry as _registry


def get_prose_connectors() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    Covers:
    - Original c09e9e64 form: "all", "every", "route", "through", ";", "no direct"
    - 15d1ac4f regression form: "continues to", "separately", "invariant",
      "whole-suite", "no behavior"
    - Policy phrases: "maintains", "preserves", "ensures", "guarantees",
      "unaffected", "continues", "regression"
    """
    return _registry()


__all__ = ["get_prose_connectors"]
